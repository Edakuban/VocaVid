import unittest

from musicvideogen.comfy import load_workflow_from_data, with_output_prefix


class ComfyWorkflowConversionTests(unittest.TestCase):
    def test_ui_workflow_is_converted_to_api_prompt_format(self):
        workflow = {
            "nodes": [
                {
                    "id": 35,
                    "type": "MarkdownNote",
                    "inputs": [],
                    "widgets_values": ["notes"],
                },
                {
                    "id": 57,
                    "type": "SubgraphThing",
                    "inputs": [{"name": "text", "type": "STRING", "link": None}],
                    "widgets_values": [],
                },
                {
                    "id": 9,
                    "type": "SaveImage",
                    "inputs": [{"name": "images", "type": "IMAGE", "link": 62}],
                    "widgets_values": ["prefix"],
                },
            ],
            "links": [[62, 57, 0, 9, 0, "IMAGE"]],
        }

        api = load_workflow_from_data(workflow)

        self.assertNotIn("35", api)
        self.assertEqual(api["57"]["class_type"], "SubgraphThing")
        self.assertEqual(api["57"]["inputs"]["text"], "{{ prompt }}")
        self.assertEqual(api["9"]["inputs"]["images"], ["57", 0])
        self.assertEqual(api["9"]["inputs"]["filename_prefix"], "prefix")

    def test_api_prompt_format_is_left_unchanged(self):
        workflow = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{ prompt }}"}}}

        self.assertEqual(load_workflow_from_data(workflow), workflow)

    def test_ui_subgraph_is_flattened_to_inner_nodes(self):
        workflow = {
            "nodes": [
                {
                    "id": 57,
                    "type": "subgraph-abc",
                    "inputs": [{"name": "text", "type": "STRING", "link": None}],
                    "outputs": [{"links": [62]}],
                    "widgets_values": [],
                },
                {
                    "id": 9,
                    "type": "SaveImage",
                    "inputs": [{"name": "images", "type": "IMAGE", "link": 62}],
                    "widgets_values": ["prefix"],
                },
            ],
            "links": [[62, 57, 0, 9, 0, "IMAGE"]],
            "definitions": {
                "subgraphs": [
                    {
                        "id": "subgraph-abc",
                        "inputs": [{"name": "text", "linkIds": [34]}],
                        "outputs": [{"linkIds": [16]}],
                        "nodes": [
                            {
                                "id": 27,
                                "type": "CLIPTextEncode",
                                "inputs": [{"name": "text", "type": "STRING", "link": 34}],
                                "widgets_values": ["old"],
                            },
                            {
                                "id": 8,
                                "type": "VAEDecode",
                                "inputs": [{"name": "samples", "type": "LATENT", "link": None}],
                                "widgets_values": [],
                            },
                        ],
                        "links": [
                            {"id": 34, "origin_id": -10, "origin_slot": 0, "target_id": 27, "target_slot": 0, "type": "STRING"},
                            {"id": 16, "origin_id": 8, "origin_slot": 0, "target_id": -20, "target_slot": 0, "type": "IMAGE"},
                        ],
                    }
                ]
            },
        }

        api = load_workflow_from_data(workflow)

        self.assertNotIn("57", api)
        self.assertEqual(api["57_27"]["class_type"], "CLIPTextEncode")
        self.assertEqual(api["57_27"]["inputs"]["text"], "{{ prompt }}")
        self.assertEqual(api["9"]["inputs"]["images"], ["57_8", 0])

    def test_ui_widget_values_fill_common_comfy_node_inputs(self):
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "KSampler",
                    "inputs": [
                        {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
                        {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
                    ],
                    "widgets_values": [123, "randomize", 8, 1, "res_multistep", "simple", 1],
                },
                {
                    "id": 2,
                    "type": "EmptySD3LatentImage",
                    "inputs": [
                        {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
                        {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
                    ],
                    "widgets_values": [1024, 768, 1],
                },
                {
                    "id": 3,
                    "type": "CLIPLoader",
                    "inputs": [{"name": "clip_name", "type": "COMBO", "link": None, "widget": {"name": "clip_name"}}],
                    "widgets_values": ["qwen_3_4b.safetensors", "lumina2", "default"],
                },
            ],
            "links": [],
        }

        api = load_workflow_from_data(workflow)

        self.assertEqual(api["1"]["inputs"]["cfg"], 1)
        self.assertEqual(api["1"]["inputs"]["sampler_name"], "res_multistep")
        self.assertEqual(api["1"]["inputs"]["scheduler"], "simple")
        self.assertEqual(api["1"]["inputs"]["denoise"], 1)
        self.assertEqual(api["2"]["inputs"]["batch_size"], 1)
        self.assertEqual(api["3"]["inputs"]["type"], "lumina2")
        self.assertEqual(api["3"]["inputs"]["device"], "default")

    def test_output_prefix_can_be_forced_without_mutating_template(self):
        workflow = {
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "old", "images": ["8", 0]}},
            "8": {"class_type": "VAEDecode", "inputs": {}},
        }

        updated = with_output_prefix(workflow, "musicvideogen/project-1/line-0-123")

        self.assertEqual(updated["9"]["inputs"]["filename_prefix"], "musicvideogen/project-1/line-0-123")
        self.assertEqual(workflow["9"]["inputs"]["filename_prefix"], "old")
