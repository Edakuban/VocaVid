import unittest

from VocaVid.comfy import ComfyClient


class FakeTransport:
    def __init__(self):
        self.posts = []
        self.history_calls = 0

    def post_json(self, url, payload):
        self.posts.append((url, payload))
        return {"prompt_id": "abc123"}

    def get_json(self, url):
        self.history_calls += 1
        return {
            "abc123": {
                "status": {"completed": True},
                "outputs": {
                    "9": {
                        "images": [
                            {
                                "filename": "line.png",
                                "subfolder": "mv",
                                "type": "output",
                            }
                        ]
                    }
                },
            }
        }


class ComfyTests(unittest.TestCase):
    def test_comfy_client_submits_template_with_variables_and_extracts_output(self):
        transport = FakeTransport()
        client = ComfyClient("http://127.0.0.1:8188", transport=transport)
        template = {"positive": "{{ lyric_text }} in {{ global_style }}"}

        result = client.run_workflow(
            template,
            {
                "lyric_text": "Hello",
                "global_style": "cinematic neon",
            },
            poll_interval_sec=0,
            timeout_sec=1,
        )

        self.assertEqual(
            transport.posts,
            [
                (
                    "http://127.0.0.1:8188/prompt",
                    {"prompt": {"positive": "Hello in cinematic neon"}},
                )
            ],
        )
        self.assertEqual(result.prompt_id, "abc123")
        self.assertEqual(result.output_files, ["mv/line.png"])

    def test_comfy_client_reports_failed_jobs(self):
        class FailedTransport(FakeTransport):
            def get_json(self, url):
                return {
                    "abc123": {
                        "status": {
                            "completed": False,
                            "status_str": "error",
                            "messages": ["bad workflow"],
                        }
                    }
                }

        client = ComfyClient("http://127.0.0.1:8188", transport=FailedTransport())

        result = client.run_workflow({"x": "{{ value }}"}, {"value": "y"}, poll_interval_sec=0, timeout_sec=1)

        self.assertEqual(result.prompt_id, "abc123")
        self.assertFalse(result.ok)
        self.assertIn("bad workflow", result.error)

    def test_comfy_client_extracts_text_outputs(self):
        class TextTransport(FakeTransport):
            def get_json(self, url):
                return {
                    "abc123": {
                        "status": {"completed": True},
                        "outputs": {"4": {"text": ["a vivid image prompt"]}},
                    }
                }

        client = ComfyClient("http://127.0.0.1:8188", transport=TextTransport())

        result = client.run_workflow({"x": "{{ value }}"}, {"value": "y"}, poll_interval_sec=0, timeout_sec=1)

        self.assertTrue(result.ok)
        self.assertEqual(result.text_outputs, ["a vivid image prompt"])

    def test_comfy_client_extracts_singular_video_output(self):
        class VideoTransport(FakeTransport):
            def get_json(self, url):
                return {
                    "abc123": {
                        "status": {"completed": True},
                        "outputs": {
                            "341": {
                                "video": {
                                    "filename": "segment-29.mp4",
                                    "subfolder": "VocaVid/demo",
                                    "type": "output",
                                }
                            }
                        },
                    }
                }

        client = ComfyClient("http://127.0.0.1:8188", transport=VideoTransport())

        result = client.run_workflow({"x": "{{ value }}"}, {"value": "y"}, poll_interval_sec=0, timeout_sec=1)

        self.assertTrue(result.ok)
        self.assertEqual(result.output_files, ["VocaVid/demo/segment-29.mp4"])

    def test_url_transport_includes_http_error_body(self):
        import urllib.error
        from io import BytesIO

        error = urllib.error.HTTPError(
            url="http://127.0.0.1:8188/prompt",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=BytesIO(b'{\"error\":\"bad node\"}'),
        )

        self.assertIn("bad node", ComfyClient.http_error_message(error))

    def test_comfy_client_interrupts_current_execution(self):
        transport = FakeTransport()
        client = ComfyClient("http://127.0.0.1:8188", transport=transport)

        client.interrupt()

        self.assertEqual(transport.posts, [("http://127.0.0.1:8188/interrupt", {})])
