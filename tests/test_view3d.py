import math
import unittest

import numpy as np

from wop.core.geometry import Point
from wop.ui.view3d import Camera, _model_point, _Projection, revolve_ring, view_matrix
from wop.ui import view3d_constants as v

from tests.reference_program import reference_program
from wop.core.program_model.program import plan_program
from wop.ui.theme import DARK_COLORS, LIGHT_COLORS
from wop.ui.view3d import build_scene


class CutawayTests(unittest.TestCase):
    def test_the_removed_quarter_is_at_the_top_towards_the_viewer_of_the_default_camera_and_the_path_face_is_seen(self):
        import math

        projection = _Projection(Camera(), (0.0, 0.0, 0.0), 1.0, v.VIEW_WIDTH_PX, v.VIEW_HEIGHT_PX)
        middle = math.radians(v.SWEEP_START_DEG + v.SWEEP_DEG + (360.0 - v.SWEEP_DEG) / 2)
        _u, up, depth = projection.view(_model_point(1.0, 0.0, middle))
        self.assertLess(depth, 0)  # depth grows away from the viewer: this side faces the viewer
        self.assertGreater(up, 0)  # and it is above the axis on the screen


class CameraTests(unittest.TestCase):
    def test_turning_changes_the_angles_and_the_elevation_stays_in_range(self):
        camera = Camera().turned(10, 5)
        self.assertAlmostEqual(camera.azimuth_deg, v.DEFAULT_AZIMUTH_DEG + 10)
        steep = Camera().turned(0, 1000)
        self.assertEqual(steep.elevation_deg, v.MAX_ELEVATION_DEG)
        self.assertEqual(Camera().turned(0, -1000).elevation_deg, v.MIN_ELEVATION_DEG)

    def test_panning_moves_the_picture_and_adds_up(self):
        still = _Projection(Camera(), (0.0, 0.0, 0.0), 1.0, v.VIEW_WIDTH_PX, v.VIEW_HEIGHT_PX)
        camera = Camera().panned(10, -4).panned(5, 1)
        moved = _Projection(camera, (0.0, 0.0, 0.0), 1.0, v.VIEW_WIDTH_PX, v.VIEW_HEIGHT_PX)
        point = still.view((1.0, 0.5, 0.25))
        (x0, y0), (x1, y1) = still.pixel(point), moved.pixel(point)
        self.assertAlmostEqual(x1 - x0, 15)
        self.assertAlmostEqual(y1 - y0, -3)
        self.assertEqual(camera.zoom, 1.0)  # panning does not change the zoom

    def test_a_fresh_camera_is_the_reset_view(self):
        moved = Camera().panned(30, 30).zoomed(3)
        self.assertNotEqual(moved, Camera())
        fresh = Camera()
        self.assertEqual((fresh.pan_x_px, fresh.pan_y_px, fresh.zoom), (0.0, 0.0, 1.0))

    def test_zoom_stays_in_range(self):
        self.assertEqual(Camera().zoomed(1000).zoom, v.MAX_ZOOM)
        self.assertEqual(Camera().zoomed(0.0001).zoom, v.MIN_ZOOM)


class RevolveTests(unittest.TestCase):
    RING = [Point(0, 0), Point(10, 0), Point(10, 20), Point(0, 20)]  # a cylinder of radius 10 and length 20

    def _area(self, mesh):
        triangles = mesh.positions.reshape(-1, 3, 3).astype(float)
        cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        return float(np.linalg.norm(cross, axis=1).sum() / 2)

    def test_the_surface_of_a_cylinder_has_the_right_area(self):
        sweep = math.radians(v.SWEEP_DEG)
        angles = [sweep * k / 90 for k in range(91)]
        mesh = revolve_ring(self.RING, angles, v.SURFACE_RGB)
        # the side, and the disc at each end (the edge on the axis has no surface)
        expected = sweep * (10 * 20 + 2 * 10 * 10 / 2)
        self.assertAlmostEqual(self._area(mesh) / expected, 1.0, delta=0.002)

    def test_the_normals_are_unit_vectors_that_stand_square_to_the_faces(self):
        angles = [math.radians(a) for a in range(0, 271, 5)]
        mesh = revolve_ring(self.RING, angles, v.SURFACE_RGB)
        self.assertTrue(np.allclose(np.linalg.norm(mesh.normals, axis=1), 1.0, atol=1e-5))
        triangles = mesh.positions.reshape(-1, 3, 3).astype(float)
        normals = mesh.normals.reshape(-1, 3, 3).astype(float)
        face = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        length = np.linalg.norm(face, axis=1)
        real = length > 1e-9  # a triangle that touches the axis along an edge can be flat
        face = face[real] / length[real][:, None]
        for corner in range(3):
            across = np.abs((face * normals[real][:, corner]).sum(axis=1))
            self.assertTrue(np.all(across > 0.99))

    def test_every_vertex_has_a_colour_and_triangles_come_in_threes(self):
        mesh = revolve_ring(self.RING, [0.0, 1.0, 2.0], v.SURFACE_RGB)
        self.assertEqual(mesh.count % 3, 0)
        self.assertEqual(mesh.positions.shape, mesh.normals.shape)
        self.assertEqual(mesh.positions.shape, mesh.colors.shape)
        self.assertTrue(np.allclose(mesh.colors[0], np.array(v.SURFACE_RGB) / 255))

    def test_an_outline_on_the_axis_only_has_no_surface(self):
        self.assertEqual(revolve_ring([Point(0, 0), Point(0, 5), Point(0, 3)], [0.0, 1.0], v.SURFACE_RGB).count, 0)


class MatrixTests(unittest.TestCase):
    def test_the_matrix_puts_a_point_where_the_projection_puts_it(self):
        camera = Camera(azimuth_deg=20, elevation_deg=-40, zoom=1.7, pan_x_px=30, pan_y_px=-12)
        centre, radius, width, height = (5.0, 0.0, 0.0), 40.0, 800.0, 500.0
        projection = _Projection(camera, centre, radius, width, height)
        mvp, _normal = view_matrix(projection, width, height, radius)
        for point in ((0.0, 10.0, 3.0), (12.0, -7.0, 20.0), (-8.0, 0.0, 0.0)):
            clip = mvp @ np.array([*point, 1.0])
            x_px, y_px = projection.pixel(projection.view(point))
            self.assertAlmostEqual((clip[0] + 1) / 2 * width, x_px, places=6)
            self.assertAlmostEqual((1 - clip[1]) / 2 * height, y_px, places=6)
            self.assertAlmostEqual(clip[3], 1.0)

    def test_a_point_nearer_to_the_viewer_has_the_smaller_depth(self):
        projection = _Projection(Camera(), (0.0, 0.0, 0.0), 10.0, 600.0, 400.0)
        mvp, _normal = view_matrix(projection, 600.0, 400.0, 10.0)
        middle = math.radians(v.SWEEP_START_DEG + v.SWEEP_DEG + (360.0 - v.SWEEP_DEG) / 2)
        near = (mvp @ np.array([*_model_point(5.0, 0.0, middle), 1.0]))[2]
        far = (mvp @ np.array([*_model_point(5.0, 0.0, middle + math.pi), 1.0]))[2]
        self.assertLess(near, far)
        self.assertTrue(-1 < near < 1 and -1 < far < 1)

    def test_the_normal_matrix_turns_without_changing_lengths(self):
        projection = _Projection(Camera(azimuth_deg=33, elevation_deg=-20), (0.0, 0.0, 0.0), 10.0, 600.0, 400.0)
        _mvp, normal = view_matrix(projection, 600.0, 400.0, 10.0)
        self.assertTrue(np.allclose(normal @ normal.T, np.eye(3)))


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan_program(reference_program())

    def _section(self, scene):
        tan = np.array(v.CUT_FACE_RGB) / 255
        return np.all(np.isclose(scene.solid.colors, tan, atol=1e-4), axis=1)

    def test_the_scene_has_triangles_the_axis_and_both_cut_sections(self):
        scene = build_scene(self.plan)
        self.assertGreater(scene.solid.count, 1000)
        self.assertEqual(scene.solid.count % 3, 0)
        self.assertGreater(len(scene.axis), 0)
        self.assertEqual(scene.glass.count, 0)
        sections = self._section(scene).sum()
        self.assertGreater(sections, 0)
        self.assertEqual(sections % 6, 0)  # triangles of two flat faces, the same at both ends
        self.assertTrue(np.all(np.isfinite(scene.solid.positions)))

    def test_the_cross_section_has_the_area_of_the_material(self):
        scene = build_scene(self.plan, upto_block=1)
        region = self.plan.blocks[1].residual_after
        triangles = scene.solid.positions[self._section(scene)].reshape(-1, 3, 3).astype(float)
        area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1).sum() / 2
        self.assertAlmostEqual(area / 2, region.area, delta=region.area * 1e-4)  # two ends

    def test_everything_lies_inside_the_sphere_round_the_scene(self):
        scene = build_scene(self.plan, 1)
        offset = scene.solid.positions.astype(float) - np.array(scene.centre)
        self.assertLessEqual(np.linalg.norm(offset, axis=1).max(), scene.radius * 1.001)

    def test_the_colours_of_the_set_are_used_for_the_path_and_the_axis(self):
        for colors in (LIGHT_COLORS, DARK_COLORS):
            scene = build_scene(self.plan, upto_block=1, colors=colors)
            used = {stroke.color for stroke in scene.strokes}
            self.assertIn(colors.cut_3d, used)
            self.assertEqual(scene.axis_color, colors.axis_3d)

    def test_the_path_of_the_chosen_block_is_drawn_and_the_rapids_are_dashed(self):
        with_path = build_scene(self.plan, upto_block=1)
        without = build_scene(self.plan, upto_block=1, show_path=False)
        cutting = [s for s in with_path.strokes if s.color == LIGHT_COLORS.cut_3d]
        rapid = [s for s in with_path.strokes if s.color == LIGHT_COLORS.rapid_3d]
        self.assertTrue(cutting and rapid)
        self.assertTrue(all(not s.dash for s in cutting) and all(s.dash for s in rapid))
        self.assertLess(len(without.strokes), len(with_path.strokes))
        self.assertFalse([s for s in without.strokes if s.color in (LIGHT_COLORS.cut_3d, LIGHT_COLORS.rapid_3d)])

    def test_every_block_gives_a_scene_and_a_wrong_index_is_refused(self):
        for index in range(len(self.plan.blocks)):
            build_scene(self.plan, index)
        with self.assertRaises(ValueError):
            build_scene(self.plan, 99)

    def test_a_coarser_scene_has_fewer_triangles(self):
        fine = build_scene(self.plan, steps_per_turn=72).solid.count
        coarse = build_scene(self.plan, steps_per_turn=36).solid.count
        self.assertLess(coarse, fine)

    def test_the_finished_outline_is_a_dashed_stroke_in_the_plane_of_the_path(self):
        from wop.core.geometry import LineSegment

        outline = (LineSegment(Point(10, 0), Point(10, -20)),)
        scene = build_scene(self.plan, outline=outline)
        found = [s for s in scene.strokes if s.color == LIGHT_COLORS.finished_outline]
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].dash)
        angle = math.radians(v.PATH_PLANE_DEG)
        self.assertTrue(np.allclose(found[0].points[0], _model_point(10, 0, angle)))


if __name__ == "__main__":
    unittest.main()
