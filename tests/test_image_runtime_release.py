import base64
import io
import math
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from werkzeug.test import Client

import ai_image_api as api


def _encoded_png():
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), 'white').save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')


class _FakeModel:
    def __init__(self):
        self.config = SimpleNamespace(id2label={0: 'artificial', 1: 'human'})
        self.eval_called = False

    def eval(self):
        self.eval_called = True
        return self


class ImageRuntimeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.original_pipeline = api.pipeline
        self.original_aux_detectors = api.aux_detectors
        self.original_aux_errors = api.aux_detector_load_errors

    def tearDown(self):
        api.pipeline = self.original_pipeline
        api.aux_detectors = self.original_aux_detectors
        api.aux_detector_load_errors = self.original_aux_errors

    def test_default_runtime_matches_literal_manifest_and_local_evaluation(self):
        metadata = api.get_release_metadata()

        self.assertEqual(
            api._fingerprint(api.RELEASE_MANIFEST),
            api.RELEASE_MANIFEST_FINGERPRINT,
        )
        self.assertTrue(metadata['runtime_manifest_qualified'])
        self.assertEqual(
            metadata['runtime_qualification_reason'],
            'runtime_matches_release_manifest',
        )
        self.assertEqual(
            metadata['runtime_fingerprint'],
            metadata['release_manifest_fingerprint'],
        )
        self.assertTrue(metadata['performance_qualified'])
        self.assertEqual(
            metadata['performance_qualification_reason'],
            'local_portfolio_model_selection_passed',
        )
        self.assertTrue(metadata['release_qualified'])
        self.assertEqual(
            metadata['release_qualification_reason'],
            'runtime_performance_and_license_qualified',
        )
        self.assertEqual(metadata['local_evaluation']['sample_count'], 62)

    def test_revision_threshold_or_auxiliary_drift_fails_runtime_gate(self):
        with patch.object(api, 'MODEL_REVISION', '0' * 40):
            model_drift = api.get_release_metadata()
        with patch.object(api, 'PROCESSOR_REVISION', '1' * 40):
            processor_drift = api.get_release_metadata()
        with patch.object(api, 'THRESHOLD', 0.51):
            threshold_drift = api.get_release_metadata()
        with (
            patch.object(api, 'AUX_MODEL_NAMES', ['example/drift-detector']),
            patch.object(
                api,
                'AUX_REVISION_OVERRIDES',
                {
                    'example/drift-detector': {
                        'model_revision': '2' * 40,
                        'processor_revision': '3' * 40,
                    }
                },
            ),
        ):
            auxiliary_drift = api.get_release_metadata()

        for metadata in (
            model_drift,
            processor_drift,
            threshold_drift,
            auxiliary_drift,
        ):
            self.assertFalse(metadata['runtime_manifest_qualified'])
            self.assertEqual(
                metadata['runtime_qualification_reason'],
                'runtime_differs_from_release_manifest',
            )
            self.assertFalse(metadata['release_qualified'])
            self.assertNotEqual(
                metadata['runtime_fingerprint'],
                metadata['release_manifest_fingerprint'],
            )

    def test_threshold_validation_rejects_non_finite_or_boundary_values(self):
        for raw_value in ('', 'bad', '0', '1', '-0.1', '1.1', 'nan', 'inf'):
            value, error = api._parse_threshold(raw_value)
            self.assertIsNone(value, raw_value)
            self.assertIsNotNone(error, raw_value)

        for raw_value in ('0.01', '0.5', '0.99'):
            value, error = api._parse_threshold(raw_value)
            self.assertTrue(math.isfinite(value), raw_value)
            self.assertIsNone(error, raw_value)

    def test_unpinned_custom_auxiliary_model_is_invalid_and_load_fails_closed(self):
        with (
            patch.object(api, 'AUX_MODEL_NAMES', ['example/custom-detector']),
            patch.object(api, 'AUX_REVISION_OVERRIDES', {}),
        ):
            metadata = api.get_release_metadata()
            loaded = api.load_model()

        self.assertFalse(metadata['runtime_manifest_qualified'])
        self.assertEqual(
            metadata['runtime_qualification_reason'],
            'invalid_runtime_configuration',
        )
        self.assertTrue(metadata['configuration_errors'])
        self.assertFalse(loaded)
        self.assertIsNone(api.pipeline)

    def test_dual_runtime_uses_pinned_revisions(self):
        created = []

        class FakeDdaDetector:
            def __init__(self, device):
                self.device = device
                self.model_revision = api.VERIFIED_MODEL_REVISION
                created.append(('primary', self))

            def load(self):
                return self

        class FakeCommunityDetector:
            def __init__(self, device, input_size):
                self.device = device
                self.input_size = input_size
                self.model_revision = (
                    api.VERIFIED_AUXILIARY_MODELS[
                        'OwensLab/commfor-model-224'
                    ]['model_revision']
                )
                created.append(('auxiliary', self))

            def load(self):
                return self

        fake_runtime = types.ModuleType('image_forensics')
        fake_runtime.DualDataAlignmentDetector = FakeDdaDetector
        fake_runtime.CommunityForensicsDetector = FakeCommunityDetector

        with patch.dict(sys.modules, {'image_forensics': fake_runtime}):
            loaded = api.load_model()

        self.assertTrue(loaded)
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0][0], 'primary')
        self.assertEqual(created[0][1].model_revision, api.VERIFIED_MODEL_REVISION)
        self.assertEqual(created[1][0], 'auxiliary')
        self.assertEqual(created[1][1].input_size, 224)
        self.assertEqual(
            created[1][1].model_revision,
            api.VERIFIED_AUXILIARY_MODELS[
                'OwensLab/commfor-model-224'
            ]['model_revision'],
        )

    def test_health_exposes_separate_runtime_performance_and_license_gates(self):
        with patch.object(api, 'pipeline', object()):
            response = Client(api.app).get('/api/ai/health')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['runtime_manifest_qualified'])
        self.assertTrue(payload['performance_qualified'])
        self.assertTrue(payload['commercial_use_qualified'])
        self.assertTrue(payload['release_qualified'])
        self.assertEqual(payload['model_revision'], api.VERIFIED_MODEL_REVISION)
        self.assertEqual(
            payload['processor_revision'],
            api.VERIFIED_PROCESSOR_REVISION,
        )
        self.assertTrue(
            any(
                item['license_id'] == 'mit'
                and item['commercial_use_allowed'] is True
                for item in payload['license_review']['models']
            )
        )

    def test_detection_response_exposes_local_portfolio_qualification(self):
        fake_result = {
            'is_ai': True,
            'confidence': 99.0,
            'ai_score': 99.0,
            'real_score': 1.0,
            'ai_label': 'artificial',
            'real_label': 'human',
        }
        with (
            patch.object(api, 'pipeline', object()),
            patch.object(api, 'detect_ai', return_value=fake_result),
            patch.object(api, 'detect_with_aux_models', return_value=[]),
            patch.object(api, 'aux_detector_load_errors', []),
        ):
            response = Client(api.app).post(
                '/api/ai/detect',
                json={'image': _encoded_png()},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertTrue(payload['runtime_manifest_qualified'])
        self.assertTrue(payload['performance_qualified'])
        self.assertTrue(payload['release_qualified'])
        self.assertEqual(
            payload['release_qualification_reason'],
            'runtime_performance_and_license_qualified',
        )


if __name__ == '__main__':
    unittest.main()
