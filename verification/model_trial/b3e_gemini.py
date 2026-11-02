"""One explicit text-only Gemini 4 Argon call; disabled network by default.

No ADC/environment credentials, SDK retry, streaming, continuation, grounding,
tools, media or explicit cache. Fees are conservative standard-rate calculations
from provider token counters, not an attested invoice or balance lookup.
"""
from datetime import datetime,timezone,timedelta
from decimal import Decimal,ROUND_CEILING,localcontext
import copy,hashlib,http.client,json,re,socket,time
from pathlib import Path
from .b3e_spend import need,encoded,digest

MODEL='gemini-4-argon'
INPUT_WINDOW=1_048_576
MAX_OUTPUT=32_768
PRICE=dict(schema='b3e-argon-standard-price-v1',model=MODEL,currency='USD',input_usd_per_million='2',
    output_including_thinking_usd_per_million='10',cache_discount_used_for_budget=False,
    valid_before_utc='2026-12-01T00:00:00+00:00',verified_utc_date='2026-11-03',
    urls=['https://ai.google.dev/gemini-api/docs/latest-model?hl=en','https://ai.google.dev/gemini-api/docs/pricing',
          'https://ai.google.dev/api/generate-content','https://ai.google.dev/api/tokens',
          'https://ai.google.dev/gemini-api/docs/models/gemini-4-argon'])
PRICE_SHA256=digest(PRICE)


class ProviderStopped(ValueError):pass


def _require(value,reason):
    if not value:raise ProviderStopped('b3e_gemini_'+reason)


def price_valid(now=None,*,remaining_seconds=0):
    now=datetime.now(timezone.utc) if now is None else now
    _require(type(now) is datetime and now.tzinfo is not None,'utc_price_clock')
    end=datetime.fromisoformat(PRICE['valid_before_utc'])
    _require(now+timedelta(seconds=remaining_seconds)<end,'price_expired_or_near_boundary')


def cost_micro_usd(prompt_tokens,output_and_thinking_tokens):
    for number in (prompt_tokens,output_and_thinking_tokens):_require(type(number) is int and 0<=number<=INPUT_WINDOW,'token_count')
    with localcontext() as context:
        context.prec=40
        # USD/M times tokens equals microUSD; ceiling once, never float money.
        return int((Decimal(prompt_tokens)*Decimal(PRICE['input_usd_per_million'])+
                    Decimal(output_and_thinking_tokens)*Decimal(PRICE['output_including_thinking_usd_per_million'])).to_integral_value(rounding=ROUND_CEILING))


def build_request(system_prompt,user_prompt,*,max_output_tokens=512,thinking_level='LOW'):
    _require(type(system_prompt) is str and bool(system_prompt) and type(user_prompt) is str and bool(user_prompt),'text_prompt')
    _require(type(max_output_tokens) is int and 1<=max_output_tokens<=MAX_OUTPUT and thinking_level in ('LOW','MEDIUM','HIGH'),'generation_bounds')
    value=dict(contents=[dict(role='user',parts=[dict(text=user_prompt)])],systemInstruction=dict(parts=[dict(text=system_prompt)]),
        generationConfig=dict(candidateCount=1,maxOutputTokens=max_output_tokens,thinkingConfig=dict(thinkingLevel=thinking_level,includeThoughts=False)),
        serviceTier='standard',store=False)
    _require(len(encoded(value))<=512*1024,'request_bytes');return value


def count_tokens_payload(request):
    """Complete steering input, not a contents-only count or spending bound."""
    return dict(generateContentRequest=dict(copy.deepcopy(request),model='models/'+MODEL))


def normalize_response(response,*,max_output_tokens,expected_model_version=None):
    _require(type(response) is dict and 'error' not in response,'response_object')
    version=response.get('modelVersion');response_id=response.get('responseId')
    _require(type(version) is str and 1<=len(version)<=256 and version.startswith(MODEL),'model_version')
    _require(expected_model_version is None or version==expected_model_version,'version_changed')
    _require(type(response_id) is str and 1<=len(response_id)<=256,'response_id')
    candidates=response.get('candidates');_require(type(candidates) is list and len(candidates)==1 and type(candidates[0]) is dict,'single_candidate')
    candidate=candidates[0];finish=candidate.get('finishReason')
    _require(finish in ('STOP','MAX_TOKENS','SAFETY','RECITATION','LANGUAGE','BLOCKLIST','PROHIBITED_CONTENT','SPII','OTHER','MALFORMED_FUNCTION_CALL'),'finish_metadata')
    _require(not set(candidate)&{'groundingMetadata','groundingAttributions','urlContextMetadata'},'unexpected_external_features')
    usage=response.get('usageMetadata');_require(type(usage) is dict,'usage_required')
    required=('promptTokenCount','candidatesTokenCount','thoughtsTokenCount','totalTokenCount')
    for key in required:_require(type(usage.get(key)) is int and 0<=usage[key]<=INPUT_WINDOW,'usage_'+key)
    for key in ('cachedContentTokenCount','toolUsePromptTokenCount'):
        if key in usage:_require(type(usage[key]) is int and 0<=usage[key]<=INPUT_WINDOW,'usage_'+key)
    _require(usage.get('toolUsePromptTokenCount',0)==0,'unexpected_tool_tokens')
    _require(usage.get('serviceTier','standard') in ('standard','unspecified'),'price_tier')
    prompt=usage['promptTokenCount'];output=usage['candidatesTokenCount'];thinking=usage['thoughtsTokenCount']
    _require(usage['totalTokenCount']==prompt+output+thinking and output+thinking<=max_output_tokens,'usage_identity_or_output_bound')
    _require(usage.get('cachedContentTokenCount',0)<=prompt,'cached_subset')
    for key in ('promptTokensDetails','cacheTokensDetails','candidatesTokensDetails','toolUsePromptTokensDetails'):
        if key in usage:
            _require(type(usage[key]) is list and all(type(row) is dict and row.get('modality')=='TEXT'
                and type(row.get('tokenCount')) is int and 0<=row['tokenCount']<=INPUT_WINDOW for row in usage[key]),'unexpected_modality')
    parts=candidate.get('content',{}).get('parts',[]);_require(type(parts) is list and len(parts)<=128,'response_parts')
    text=[]
    for part in parts:
        _require(type(part) is dict and not set(part)-{'text','thought','thoughtSignature'} and type(part.get('text')) is str,'text_only_response')
        _require(part.get('thought',False) is False,'unexpected_thought_text');text.append(part['text'])
    _require(finish!='STOP' or bool(text),'empty_stop')
    receipt=dict(model_version=version,response_id=response_id,finish_reason=finish,usage=copy.deepcopy(usage),price_sha256=PRICE_SHA256,
        response_sha256=digest(response),charge_micro_usd=cost_micro_usd(prompt,output+thinking),
        charge_source='conservative_standard_rate_from_provider_usage_not_invoice',actual_invoice_cost=None,
        missing_invoice_reason='provider_did_not_supply_invoice_charge',cached_discount_claimed=False)
    return ''.join(text),receipt


def _load_explicit_key(path):
    path=Path(path);_require(path.is_absolute() and path.resolve()==path and path.is_file(),'explicit_key_unavailable')
    try:
        with path.open('rb') as stream:raw=stream.read(1025)
        key=raw.decode('ascii').strip()
        _require(len(raw)<=1024 and re.fullmatch(r'[A-Za-z0-9_-]{16,512}',key) is not None,'explicit_key_format')
    except (OSError,UnicodeError):raise ProviderStopped('b3e_gemini_explicit_key_unavailable') from None
    return key


class OfficialHTTPTransport:
    def __init__(self,*,api_key_file,enabled=False):
        _require(type(enabled) is bool,'enabled_flag');self.api_key_file=Path(api_key_file);self.enabled=enabled

    def __call__(self,request,budget):
        _require(self.enabled,'network_disabled');budget.check()
        key=_load_explicit_key(self.api_key_file);connection=http.client.HTTPSConnection('generativelanguage.googleapis.com',timeout=budget.remaining(30.))
        def stop():
            try:
                if connection.sock is not None:connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()
        unregister=budget.add_expiry_callback(stop)
        try:
            connection.request('POST','/v1beta/models/'+MODEL+':generateContent',body=encoded(request),
                headers={'Content-Type':'application/json','x-goog-api-key':key})
            budget.check()
            if connection.sock is not None:connection.sock.settimeout(budget.remaining(30.))
            response=connection.getresponse();_require(response.status==200,'http_status_'+str(response.status))
            raw=response.read(2*1024*1024+1);_require(len(raw)<=2*1024*1024,'response_bytes');budget.check()
            def unique(pairs):
                value={}
                for name,item in pairs:_require(name not in value,'duplicate_response_key');value[name]=item
                return value
            def nonfinite(value):raise ProviderStopped('b3e_gemini_nonfinite_response')
            return json.loads(raw,object_pairs_hook=unique,parse_constant=nonfinite)
        except ProviderStopped:raise
        except BaseException:raise ProviderStopped('b3e_gemini_transport_outcome_unknown') from None
        finally:key=None;unregister();stop()


def generate_once(ledger,transport,*,episode_id,request_id,system_prompt,user_prompt,budget,max_output_tokens=512,
                  thinking_level='LOW',expected_model_version=None):
    """Caller supplies the sole campaign ledger, immutable episode and gate.

    The whole context window is reserved; countTokens is not a hard input cap.
    Missing counters/version/finish/transport outcome keep that upper bound and
    stop the campaign. No retries and no new allowance are created here.
    """
    if type(transport) is OfficialHTTPTransport:_require(transport.enabled,'network_disabled')
    request=build_request(system_prompt,user_prompt,max_output_tokens=max_output_tokens,thinking_level=thinking_level)
    budget.check();price_valid(remaining_seconds=budget.remaining())
    upper=cost_micro_usd(INPUT_WINDOW,max_output_tokens);started=time.perf_counter_ns()
    with ledger.attempt(episode_id,request_id,digest(request),upper,timeout=min(2.,budget.remaining())) as permit:
        response=transport(copy.deepcopy(request),budget);budget.check();price_valid()
        text,receipt=normalize_response(response,max_output_tokens=max_output_tokens,expected_model_version=expected_model_version)
        permit.settle(receipt['charge_micro_usd'],receipt)
    return dict(text=text,receipt=receipt,request_sha256=digest(request),max_output_tokens=max_output_tokens,thinking_level=thinking_level,
        elapsed_ns=time.perf_counter_ns()-started,reserved_micro_usd=upper,campaign=ledger.snapshot(),transport_calls=1)
