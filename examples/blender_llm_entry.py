"""Start a local MCP entry for an explicitly selected rigid Blender pair."""

from human_eye_fast.blender_llm_bridge import start
from human_eye_fast.llm_entry import Binding, LLMEntry
from human_eye_fast.local_tasks import CloseGapSession, CloseGapTask


def binding_for(scene, view_layer, objects, moving_id, reference_id, *, image_mode=None, context_objects=None):
    """Bind a trusted local host to a fixed-topology rigid pair.

    The host ensures moving changes only by the requested world translation,
    reference stays fixed, and the scene stays stable through evidence reads.
    """
    if image_mode not in (None, "NATURAL", "SECTION"):
        raise ValueError("Use NATURAL, SECTION or None for image_mode")
    if not all(isinstance(key, str) and key for key in (moving_id, reference_id)):
        raise ValueError("Bind two nonempty object IDs")
    pair = {key: objects[key] for key in (moving_id, reference_id)}
    context_objects = {} if context_objects is None else dict(context_objects)
    if pair[moving_id] == pair[reference_id]:
        raise ValueError("Bind two distinct Blender objects")

    def open_task(target_gap_m, tolerance_m):
        task = CloseGapTask(moving_id, reference_id, target_gap_m, tolerance_m)
        return CloseGapSession(scene, view_layer, pair, task)

    class ConnectionRenderer:
        def __init__(self):
            self.renderer = None

        def render(self, session, readback, mode):
            if readback.surface.distance_m <= 0:
                mode = "NATURAL"
            import bpy
            from human_eye_fast.raycast_saccade_gpu import VGRenderer

            meshes, scale_length = session.evidence_meshes(readback, context_objects=context_objects)
            with bpy.context.temp_override(scene=scene, view_layer=view_layer):
                if self.renderer is None:
                    self.renderer = VGRenderer()
                renderer = self.renderer
                rendered = renderer.observe(
                    renderer.prepare(meshes), readback.surface, target_ids=readback.target_ids,
                    frame_id=readback.frame_id, scale_length=scale_length, mode=mode,
                )
            return rendered.png, rendered.metadata

        def close(self):
            renderer, self.renderer = self.renderer, None
            if renderer is not None:
                renderer.close()

    return Binding(moving_id, reference_id, open_task,
                   ConnectionRenderer if image_mode is not None else None,
                   tuple(obj.name for obj in pair.values()), image_mode or "NATURAL")


def start_bound(scene, view_layer, objects, moving_id, reference_id, *, image_mode=None,
                context_objects=None, port=0):
    """Start on Blender's main thread. Stop the returned bridge before scene reload."""
    binding = binding_for(scene, view_layer, objects, moving_id, reference_id, image_mode=image_mode,
                          context_objects=context_objects)
    return start(lambda: LLMEntry(binding), port=port)
