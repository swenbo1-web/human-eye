"""Add a read-only connector timing receipt to the qualified stdio observer."""
from pathlib import Path


if __name__=='__main__':
    prior = Path(__file__).resolve().parent.parent/'m4_source_region_selective_visual_capture_001/stdio_entry.py'
    source = prior.read_text(encoding='utf8')
    marker = "            save(publication/f'PRODUCER_{len(results)}.json',value)\n"
    if source.count(marker)!=1:
        raise ValueError('prior_stdio_instrument_anchor_changed')
    receipt = """            if arm=='B':
                wire_work = getattr(instance.host,'_last_visual_wire_work',None)
                if type(wire_work) is not dict:
                    raise ValueError('actual_private_wire_consumer_work_missing')
                save(publication/f'WIRE_WORK_{len(results)}.json',wire_work)
"""
    source = source.replace(marker,marker+receipt)
    exec(compile(source,str(prior),'exec'),{'__name__':'__main__','__file__':str(prior)})
