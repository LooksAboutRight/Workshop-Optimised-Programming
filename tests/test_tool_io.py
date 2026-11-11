import json
import unittest

from tests.helpers import simple_tool
from wop.core.files.contour_io import ContourError
from wop.core.tooling.tool import ToolError
from wop.core.files.tool_io import tool_from_dict, tool_to_dict


class ToolIoTests(unittest.TestCase):
    def test_round_trip_through_json(self):
        tool = simple_tool(3, side=-1)
        data = json.loads(json.dumps(tool_to_dict(tool)))
        self.assertEqual(tool_from_dict(data), tool)

    def test_roles_survive(self):
        tool = tool_from_dict(tool_to_dict(simple_tool(1)))
        self.assertEqual(len(tool.shape.cutter_segments), 2)
        self.assertEqual(len(tool.shape.holder_segments), 2)

    def test_damaged_data_is_refused(self):
        data = tool_to_dict(simple_tool(1))
        with self.assertRaises(ToolError):
            tool_from_dict({**data, "format": 99})
        with self.assertRaises(ToolError):
            tool_from_dict({"format": data["format"]})
        broken = dict(data, pieces=data["pieces"][:2])  # not a closed outline
        with self.assertRaises((ToolError, ContourError)):
            tool_from_dict(broken)


if __name__ == "__main__":
    unittest.main()
