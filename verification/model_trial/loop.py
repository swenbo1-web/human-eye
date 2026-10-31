"""One episode, one fresh context, provider-neutral and disabled without binding.

No provider SDK, credential lookup, network, engine, Blender, AL or hook is
imported here. SyntheticTransport is data-only contract execution and records
zero provider requests. A live adapter is deliberately not supplied.
"""
from __future__ import annotations

import copy
import dataclasses
import math
import time
from dataclasses import dataclass, field
from typing import Protocol

from .tools import ToolRejected
from .compute import ComputeError
from .spend import SharedRunBudget, SpendRejected
from .deadline import DeadlineExceeded, EpisodeDeadline


COMMON_SYSTEM_PROMPT = '完成用户指定的三维任务。可使用提供的原生观察和执行工具，也可自行编写几何计算。所有物理长度以米计算，并在答复中明确单位。只允许对指定目标做世界Z纯平移，保持世界X/Y、姿态、缩放、网格及所有其他对象。执行域限于静态、闭合凸网格与有限平行支撑面；开放网格、非凸或能力不允许时说明原因并停止，不绕过限制。只读任务不得移动。每次写入不超过1毫米，最多8次写入，累计路径不超过8毫米。不要把图像看不清、工具标签或工具自称成功当作最终质量证明；证据不足应明确说明。任务提示之外没有额外人类纠正。最终简要报告完成、未完成或拒绝、依据和剩余不确定性。'
USAGE_FIELDS = ('input', 'output', 'total', 'reasoning', 'cached', 'image')


@dataclass(frozen=True)
class EpisodeLimits:
    wall_seconds: float = 180.0
    responses: int = 12
    tools: int = 24
    output_tokens: int = 16000
    cumulative_input_tokens: int = 128000

    def __post_init__(self):
        maximum = (180, 12, 24, 16000, 128000)
        for (name, cap) in zip(self.__dataclass_fields__, maximum):
            value = getattr(self, name)
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or value <= 0 or value > cap
                    or (name != 'wall_seconds' and type(value) is not int)):
                raise ValueError('episode limit cannot exceed the frozen cap: ' + name)


@dataclass(frozen=True)
class RunBinding:
    """Frozen run settings. spend_cap is the total cap across all run episodes."""
    mode: str
    model: str
    version: str
    settings: dict
    spend_cap: float
    currency: str
    provider_adapter: str
    isolation_verified: bool
    balance_verified: bool
    fees_verified: bool
    isolation_evidence: str = ''
    usage_contract: str = ''

    def problems(self):
        issues = []
        if self.mode != 'formal':
            issues.append('binding.mode must be formal')
        for name in ('model', 'version', 'currency', 'provider_adapter', 'isolation_evidence', 'usage_contract'):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                issues.append('missing exact binding: ' + name)
        if type(self.settings) is not dict or not self.settings:
            issues.append('exact model/reasoning/sampling/image settings are unbound')
        if (type(self.spend_cap) not in (int, float) or not math.isfinite(self.spend_cap)
                or self.spend_cap <= 0):
            issues.append('authorized spend cap is missing or invalid')
        for name in ('isolation_verified', 'balance_verified', 'fees_verified'):
            if getattr(self, name) is not True:
                issues.append(name + ' is not verified')
        return issues


@dataclass(frozen=True)
class Reservation:
    """Trusted adapter's conservative maxima, not character/token estimates."""
    input_tokens_upper_bound: int
    output_tokens_upper_bound: int
    cost_upper_bound: float
    balance_available: float
    currency: str
    caps_verified: bool
    fee_source: str
    reservation_id: str


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict
    id: str = ''


@dataclass(frozen=True)
class NormalizedResponse:
    text: str = ''
    tool_calls: tuple = ()
    usage: dict | None = None
    raw_usage: dict | None = None
    usage_reasons: dict = field(default_factory=dict)
    finish_reason: str | None = None
    actual_cost: float | None = None
    actual_cost_source: str | None = None


class ProviderAdapter(Protocol):
    identity: str
    deadline_enforced: bool
    usage_verified: bool

    def bind_deadline(self, budget: EpisodeDeadline): ...

    def reserve(self, request: dict) -> Reservation: ...
    def __call__(self, request: dict) -> NormalizedResponse: ...


class SyntheticTransport:
    """A finite list of normalized data; not a proxy to a live provider callable."""
    def __init__(self, responses):
        self._responses = copy.deepcopy(list(responses))
        self._index = 0
        self.requests = []

    def __call__(self, request):
        self.requests.append(copy.deepcopy(request))
        if self._index >= len(self._responses):
            raise ValueError('synthetic response list exhausted')
        response = self._responses[self._index]
        self._index += 1
        return response


@dataclass
class EpisodeResult:
    arm: str
    status: str = 'disabled'
    formal: bool = False
    formal_eligible: bool = False
    provider_requests: int = 0
    model_responses: int = 0
    tool_requests: int = 0
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    reserved_spend_upper_bound: float = 0.0
    run_spend: dict | None = None
    run_reservations: list = field(default_factory=list)
    actual_cost: float | None = None
    actual_cost_missing_reason: str | None = 'provider_actual_charge_not_reported'
    currency: str | None = None
    final_text: str = ''
    elapsed_s: float = 0.0
    stop_reason: str | None = None
    failures: list = field(default_factory=list)
    usage: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    binding: dict | None = None
    limits: dict = field(default_factory=dict)

    def to_dict(self):
        return dataclasses.asdict(self)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)


def normalize_usage(usage=None, raw=None, reasons=None):
    """No guessed tokens or derived provider fields. Missing values remain null."""
    if usage is not None and type(usage) is not dict:
        raise ValueError('normalized usage must be an object or null')
    if raw is not None and type(raw) is not dict:
        raise ValueError('raw usage must be an object or null')
    values = {}
    missing = {}
    for name in USAGE_FIELDS:
        value = (usage or {}).get(name)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError('usage must contain nonnegative actual integer counters')
        values[name] = value
        if value is None:
            missing[name] = (reasons or {}).get(name, 'provider_did_not_report')
    return {'values': values, 'missing_reasons': missing,
            'raw': copy.deepcopy(raw if raw is not None else usage),
            'raw_source': 'provider_adapter_raw_usage' if raw is not None else
                          'normalized_only_raw_provider_usage_not_supplied'}


def _response(value):
    if type(value) is dict:
        allowed = {field.name for field in dataclasses.fields(NormalizedResponse)}
        if value.keys() - allowed:
            raise ValueError('unknown normalized response fields')
        value = NormalizedResponse(**value)
    if type(value) is not NormalizedResponse or type(value.text) is not str:
        raise ValueError('provider response is not normalized')
    calls = []
    if type(value.tool_calls) not in (list, tuple):
        raise ValueError('tool_calls must be an array')
    for call in value.tool_calls:
        if type(call) is dict:
            if call.keys() - {'name', 'arguments', 'id'}:
                raise ValueError('unknown tool call fields')
            call = ToolCall(**call)
        if (type(call) is not ToolCall or type(call.name) is not str
                or type(call.arguments) is not dict or type(call.id) is not str):
            raise ValueError('invalid normalized tool call')
        calls.append(call)
    return dataclasses.replace(value, tool_calls=tuple(calls))


def _reservation(value, request, result, binding, limits):
    if type(value) is dict:
        value = Reservation(**value)
    if type(value) is not Reservation:
        raise ValueError('trusted adapter did not supply a reservation')
    for name in ('input_tokens_upper_bound', 'output_tokens_upper_bound'):
        number = getattr(value, name)
        if type(number) is not int or number <= 0:
            raise ValueError('reservation needs positive conservative token maxima')
    for name in ('cost_upper_bound', 'balance_available'):
        number = getattr(value, name)
        if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
            raise ValueError('reservation lacks verifiable finite money bounds')
    if (value.caps_verified is not True or not value.fee_source or not value.reservation_id
            or value.currency != binding.currency):
        raise ValueError('provider fee/caps/currency reservation is unverified')
    if result.input_tokens is None or result.output_tokens is None:
        raise ValueError('actual token accounting is unavailable')
    if result.input_tokens + value.input_tokens_upper_bound > limits.cumulative_input_tokens:
        raise ValueError('conservative input reservation exceeds cumulative token cap')
    if result.output_tokens + value.output_tokens_upper_bound > limits.output_tokens:
        raise ValueError('conservative output reservation exceeds token cap')
    if value.output_tokens_upper_bound > request['max_output_tokens']:
        raise ValueError('adapter output reservation exceeds request output cap')
    if (result.reserved_spend_upper_bound + value.cost_upper_bound > binding.spend_cap
            or value.cost_upper_bound > value.balance_available):
        raise ValueError('conservative reservation exceeds authorized spend or verified balance')
    return value


def run_episode(provider, router, user_prompt, binding=None, synthetic=False,
                clock=time.monotonic, limits=None, run_budget=None, episode_id=None):
    """Run a single context. Formal admission is fail closed before any request.

    A real adapter must enforce the absolute deadline across provider transport,
    and native/plugin adapters must enforce it across their respective hosts.
    Missing raw/actual usage invalidates the episode and prevents a next request.
    Every formal episode must share the runner's one SharedRunBudget and a unique
    episode_id. Binding.spend_cap denotes the entire run, not an episode refill.
    No synthetic episode can mark itself formal or consume the shared ledger.
    """
    started = clock()  # includes context assembly, schemas, calls, capture, transfer
    limits = limits or EpisodeLimits()
    if type(limits) is not EpisodeLimits:
        raise ValueError('limits must be frozen EpisodeLimits')
    result = EpisodeResult(arm=router.arm, limits=dataclasses.asdict(limits))
    budget = None
    def wall_exhausted():
        if budget is not None:
            try:
                budget.check()
            except DeadlineExceeded:
                return True
        return clock() >= started + limits.wall_seconds
    def finish(status, reason=None):
        if status == 'completed' and wall_exhausted():
            status, reason = 'budget_stopped', 'external_wall_time_before_completion'
            result.final_text = ''
        result.status = status
        result.stop_reason = reason
        result.elapsed_s = max(0.0, clock() - started)
        result.formal_eligible = bool(result.formal and status == 'completed' and not result.failures
                                      and not router.partial)
        if result.formal and type(run_budget) is SharedRunBudget:
            result.run_spend = run_budget.snapshot()
        router.end_episode()
        return result
    if type(user_prompt) is not str or not user_prompt.strip():
        return finish('disabled', 'user prompt is missing')
    if router.events:
        return finish('disabled', 'episode requires a fresh router with no inherited tool events')
    if synthetic:
        if type(provider) is not SyntheticTransport:
            return finish('disabled', 'offline contracts require the data-only SyntheticTransport')
        result.formal = False
        result.actual_cost_missing_reason = 'offline_contract_no_provider_requests'
    else:
        issues = []
        if type(binding) is not RunBinding:
            issues.append('complete explicit RunBinding is required; no live adapter is bundled')
        else:
            issues.extend(binding.problems())
            result.binding = dataclasses.asdict(binding)
            result.currency = binding.currency
            if getattr(provider, 'identity', None) != binding.provider_adapter:
                issues.append('provider adapter identity does not match binding')
            if type(run_budget) is not SharedRunBudget:
                issues.append('one shared run-wide reservation ledger is required')
            else:
                try:
                    if not run_budget.matches_binding(binding.spend_cap, binding.currency):
                        issues.append('run ledger total cap/currency differs from binding')
                except SpendRejected:
                    issues.append('run ledger cap binding is invalid')
        if type(episode_id) is not str or not episode_id.strip() or len(episode_id) > 256:
            issues.append('unique run-wide episode_id is required')
        if not callable(getattr(provider, 'bind_deadline', None)):
            issues.append('provider cannot bind the shared absolute deadline')
        if getattr(provider, 'usage_verified', False) is not True:
            issues.append('provider actual/raw usage contract is unverified')
        if not callable(getattr(provider, 'reserve', None)):
            issues.append('provider conservative caps/fee/balance reservation is unavailable')
        for adapter in [router.native] + ([router.plugin] if router.plugin is not None else []):
            if not callable(getattr(adapter, 'bind_deadline', None)):
                issues.append('tool host cannot bind the shared absolute deadline')
        if issues:
            result.failures.extend(issues)
            return finish('disabled', 'formal launch preflight failed')
        try:
            run_budget.claim_episode(episode_id)
        except SpendRejected:
            result.failures.append('episode identity or global episode count rejected by run ledger')
            return finish('disabled', 'run_episode_admission_failed')
    # One immutable start includes admission/context/schema assembly and lazy
    # startup. Binding itself must neither call the provider nor start a host.
    budget = EpisodeDeadline(limits.wall_seconds, clock=clock, started=started,
                            watchdog=clock is time.monotonic)
    deadline = budget.expires_at
    try:
        router.bind_deadline(budget, require_adapters=not synthetic)
        if not synthetic:
            provider.bind_deadline(budget)
            if (getattr(provider, 'bound_deadline', None) is not budget
                    or getattr(provider, 'deadline_enforced', False) is not True):
                raise ValueError('provider shared deadline is not verified')
            for adapter in [router.native] + ([router.plugin] if router.plugin is not None else []):
                if getattr(adapter, 'deadline_enforced', False) is not True:
                    raise ValueError('bound tool deadline is not verified')
            result.formal = True
        budget.check()
    except Exception as exc:
        result.failures.append('shared deadline binding rejected: ' + type(exc).__name__)
        budget.expire('deadline_binding_failed')
        return finish('disabled', 'shared_deadline_binding_failed')
    # Fresh local messages; no provider conversation ID or previous messages accepted.
    result.messages = [{'role': 'system', 'content': COMMON_SYSTEM_PROMPT},
                       {'role': 'user', 'content': user_prompt}]
    try:
        budget.check()
        tool_schemas = router.tool_schemas()
        budget.check()
    except DeadlineExceeded:
        return finish('budget_stopped', 'external_wall_time_during_context')
    costs = []
    for index in range(limits.responses):
        if wall_exhausted():
            return finish('budget_stopped', 'external_wall_time')
        if result.output_tokens is not None and result.output_tokens >= limits.output_tokens:
            return finish('budget_stopped', 'output_token_cap')
        request = {'messages': copy.deepcopy(result.messages), 'tools': copy.deepcopy(tool_schemas),
                   'max_output_tokens': limits.output_tokens - (result.output_tokens or 0),
                   'deadline_monotonic': deadline,
                   'model': binding.model if result.formal else 'offline-synthetic',
                   'version': binding.version if result.formal else 'contract-only',
                   'settings': copy.deepcopy(binding.settings) if result.formal else {},
                   'response_index': index}
        reservation = None
        if result.formal:
            try:
                reservation = _reservation(provider.reserve(copy.deepcopy(request)), request,
                                           result, binding, limits)
                shared_receipt = run_budget.reserve(episode_id, reservation.reservation_id,
                                                    reservation.cost_upper_bound,
                                                    reservation.balance_available,
                                                    reservation.currency)
            except Exception as exc:
                result.failures.append('reservation rejected: ' + type(exc).__name__)
                return finish('disabled' if not result.provider_requests else 'invalid', 'preflight_reservation_failed')
            result.run_reservations.append(shared_receipt)
            result.reserved_spend_upper_bound += reservation.cost_upper_bound
        if wall_exhausted():
            return finish('budget_stopped', 'external_wall_time_before_request')
        call_started = clock()
        if result.formal:
            result.provider_requests += 1  # attempts, including failures, may cost money
        try:
            response = _response(provider(request))
        except Exception as exc:
            result.failures.append('transport/normalization failed: ' + type(exc).__name__)
            return finish('invalid', 'provider_or_transport_failure')
        result.model_responses += 1
        try:
            usage = normalize_usage(response.usage, response.raw_usage, response.usage_reasons)
        except ValueError:
            result.failures.append('provider usage counters invalid')
            return finish('invalid', 'invalid_provider_usage')
        result.usage.append(usage)
        values = usage['values']
        for name, attr in [('input', 'input_tokens'), ('output', 'output_tokens')]:
            actual = values[name]
            previous = getattr(result, attr)
            setattr(result, attr, None if actual is None or previous is None else previous + actual)
        result.trace.append({'event': 'model_response', 'response_index': index,
                             'elapsed_s': clock() - call_started,
                             'text': response.text, 'tool_calls': [dataclasses.asdict(c) for c in response.tool_calls],
                             'usage': usage, 'reservation': dataclasses.asdict(reservation) if reservation else None,
                             'finish_reason': response.finish_reason,
                             'actual_cost': response.actual_cost,
                             'actual_cost_source': response.actual_cost_source})
        if response.actual_cost is not None:
            if (type(response.actual_cost) not in (int, float) or not math.isfinite(response.actual_cost)
                    or response.actual_cost < 0 or not response.actual_cost_source):
                result.failures.append('actual charge lacks verifiable amount/source')
                return finish('invalid', 'invalid_cost_receipt')
            costs.append(response.actual_cost)
            result.actual_cost = sum(costs) if len(costs) == result.model_responses else None
            if result.actual_cost is not None:
                result.actual_cost_missing_reason = None
        if result.formal:
            if (any(values[name] is None for name in ('input', 'output', 'total'))
                    or response.raw_usage is None):
                result.failures.append('required actual/raw provider metering is missing')
                return finish('invalid', 'missing_provider_metering')
            if (values['input'] > reservation.input_tokens_upper_bound
                    or values['output'] > reservation.output_tokens_upper_bound
                    or (response.actual_cost is not None and response.actual_cost > reservation.cost_upper_bound)):
                result.failures.append('provider actual usage/charge exceeded its conservative reservation')
                return finish('invalid', 'provider_reservation_contract_broken')
        if wall_exhausted():
            return finish('budget_stopped', 'external_wall_time_after_response')
        if (result.input_tokens is not None and result.input_tokens > limits.cumulative_input_tokens
                or result.output_tokens is not None and result.output_tokens > limits.output_tokens):
            return finish('budget_stopped', 'actual_token_cap')
        result.messages.append({'role': 'assistant', 'content': response.text,
                                'tool_calls': [dataclasses.asdict(c) for c in response.tool_calls]})
        if not response.tool_calls:
            result.final_text = response.text
            if router.partial:
                result.failures.append('one or more tool results had unverifiable partial projection')
            return finish('completed')
        for call_index, call in enumerate(response.tool_calls):
            if result.tool_requests >= limits.tools:
                return finish('budget_stopped', 'tool_request_cap')
            if wall_exhausted():
                return finish('budget_stopped', 'external_wall_time_before_tool')
            result.tool_requests += 1
            call_id = call.id or f'r{index}t{call_index}'
            tool_started = clock()
            try:
                tool_result = router.call(call.name, call.arguments)
            except Exception as exc:
                if (getattr(exc, 'uncertain', False) or getattr(router, 'poisoned', False)):
                    result.failures.append('unconfirmed tool outcome; execution stopped without retry')
                    result.trace.append({'event': 'unconfirmed_tool_outcome', 'tool_call_id': call_id,
                                         'name': call.name, 'elapsed_s': clock() - tool_started})
                    return finish('invalid', 'unconfirmed_tool_outcome')
                # Never echo Python exception messages containing host paths/state.
                tool_result = {'error': 'tool_request_rejected', 'category': type(exc).__name__}
                if type(exc) in (ToolRejected, ComputeError):
                    # These two local types construct only bounded interpreter/
                    # schema diagnostics. Arbitrary host exception text stays out.
                    tool_result['detail'] = str(exc)
            result.trace.append({'event': 'tool_result', 'tool_call_id': call_id,
                                 'name': call.name, 'arguments': copy.deepcopy(call.arguments),
                                 'elapsed_s': clock() - tool_started, 'result': tool_result})
            result.messages.append({'role': 'tool', 'tool_call_id': call_id,
                                    'name': call.name, 'content': tool_result})
            if wall_exhausted():
                return finish('budget_stopped', 'external_wall_time_after_tool')
    return finish('budget_stopped', 'model_response_cap')
