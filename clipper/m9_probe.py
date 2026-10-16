"""Read-only import/filter probe; does not claim account/model/device acceptance."""
import json
import sys
from .m9_contract import VERSION
from .m9_media import available_filters


def main():
    import clipper.m8,clipper.m9,clipper.api_m9,clipper.m8_cli
    filters=available_filters()
    print(json.dumps({'version':VERSION,'python':sys.version.split()[0],'core_imports':'passed',
        'ffmpeg_filters':sorted(filters),'capture_devices':'native_test_required','neural_models':'actual_inference_not_probed',
        'live_accounts':'not_connected_by_probe','native_editor_import':'not_tested','paid_api_required':False},indent=2))
    return 0 if {'scale','overlay','eq','hqdn3d'}.issubset(filters) else 1


if __name__=='__main__':raise SystemExit(main())
