"""Group B command line interface; paths are relative to the current directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from agriscan.io.image_validator import validate_survey_folder
from agriscan.io.metadata_reader import read_metadata
from agriscan.io.raw_reader import read_raw
from agriscan.pipeline.runner import analyze_existing, run_demo, run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description='AgriScan: RAW → ODM → NDVI/grid → alerts A/B')
    commands = parser.add_subparsers(dest='command', required=True)
    process = commands.add_parser('process', aliases=['run'], help='Run the complete RAW survey pipeline')
    process.add_argument('--input', type=Path, default=Path('assets'))
    process.add_argument('--output', type=Path)
    process.add_argument('--config', type=Path, help='Optional workflow YAML override')
    process.add_argument('--boundary', type=Path, help='Optional WGS84 plot Polygon GeoJSON')
    process.add_argument('--experimental', action='store_true', help='Allow unvalidated relative NDVI; no cross-survey comparison')
    analyze = commands.add_parser('analyze', help='Analyze an existing verified 3-band linear float32 mosaic')
    analyze.add_argument('mosaic', type=Path)
    analyze.add_argument('--survey-id', required=True)
    analyze.add_argument('--plot-id', required=True)
    analyze.add_argument('--output', type=Path)
    analyze.add_argument('--config', type=Path)
    analyze.add_argument('--boundary', type=Path)
    analyze.add_argument('--experimental', action='store_true')
    demo = commands.add_parser('demo', help='Synthetic GIS demo; does not run ODM')
    demo.add_argument('--output', type=Path)
    demo.add_argument('--config', type=Path)
    validate = commands.add_parser('validate', help='Validate a Group A survey directory')
    validate.add_argument('survey_dir', type=Path)
    raw = commands.add_parser('read-raw', help='Decode and inspect a MAPIR RAW image')
    raw.add_argument('raw_path', type=Path)
    raw.add_argument('--metadata', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'validate':
            report = validate_survey_folder(args.survey_dir)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            if not report['is_valid']:
                raise SystemExit(1)
        elif args.command == 'read-raw':
            metadata = read_metadata(args.metadata, strict=False) if args.metadata else None
            _, report = read_raw(args.raw_path, survey_metadata=metadata)
            print(json.dumps(report, indent=2, ensure_ascii=False))
        elif args.command == 'demo':
            run_demo(output_dir=args.output, config_path=args.config)
        elif args.command == 'analyze':
            analyze_existing(args.mosaic, survey_id=args.survey_id, plot_id=args.plot_id,
                             output_dir=args.output, config_path=args.config,
                             experimental=args.experimental, boundary_path=args.boundary)
        else:
            run_pipeline(args.config, args.input, output_dir=args.output,
                         experimental=args.experimental, boundary_path=args.boundary)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print('Cancelled; prior successful output is preserved.', file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == '__main__':
    main()
