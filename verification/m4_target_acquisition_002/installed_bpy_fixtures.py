from types import SimpleNamespace as NS

class FakeMatrix(list):
    pass

def matrix(translation=(0, 0, 0), scales=(1, 1, 1)):
    return FakeMatrix([[scales[0], 0., 0., translation[0]],
                       [0., scales[1], 0., translation[1]],
                       [0., 0., scales[2], translation[2]], [0., 0., 0., 1.]])

class FakeMesh:
    def __init__(self):
        self.vertices = [NS(co=p) for p in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))]
        self.loop_triangles = [NS(vertices=f) for f in ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))]
        self.shape_keys = self.animation_data = None

    def calc_loop_triangles(self):
        pass

class FakeObject:
    def __init__(self, name, translation=(0, 0, 0)):
        self.name = self.name_full = name
        self.type, self.instance_type, self.mode = "MESH", "NONE", "OBJECT"
        self.is_instancer = False
        self.library = self.parent = self.animation_data = self.rigid_body = self.rigid_body_constraint = None
        self.children, self.constraints, self.modifiers = [], [], []
        self.color = (0.5, 0.25, 1., 1.)
        self.lock_location = self.lock_rotation = self.lock_scale = (False, False, False)
        self.data = FakeMesh()
        self._matrix_world = matrix(translation)
        self.assignments = self.clears = 0
        self.hide_viewport = self.hide_render = False
        self.fail_read_after_assignment = False
        self._failed_once = False

    @property
    def matrix_world(self):
        return self._matrix_world

    @matrix_world.setter
    def matrix_world(self, value):
        self.assignments += 1
        self._matrix_world = FakeMatrix([list(row) for row in value])

    def evaluated_get(self, graph):
        return self

    def to_mesh(self):
        if self.fail_read_after_assignment and self.assignments == 1 and not self._failed_once:
            self._failed_once = True
            raise RuntimeError("Simulated evaluation failure")
        return self.data

    def to_mesh_clear(self):
        self.clears += 1
