# Generated SVG compaction

`--optimize-svg` / `VectorizeOptions(optimize_svg=True)` is a conservative,
optional postprocessing step for Vectorize output. It runs on the isolated
staged SVG after XML validation and before atomic publication, then validates
again. Only a smaller result is retained. Final metrics include compaction.

## Evaluation

[Scour](https://github.com/scour-project/scour) provides broader structure and
path optimization; its options can change numeric precision, IDs and geometry
representation. [SVGO](https://github.com/svg/svgo) adds a Node runtime to this
Python/standalone application. Neither dependency is needed for a first,
conservative transform of VTracer's simple path output.

The internal transform removes indentation in known SVG containers and optional
whitespace around SVG path command letters. It retains numeric strings exactly,
including exponent notation and arc flags. It preserves attributes such as
viewBox, transforms, gradient references, alpha, namespace bindings, comments,
and significant text. Text/style/script/foreign content is not traversed, and
`xml:space="preserve"` protects container text. It does not merge paths, round
coordinates, remove IDs, or optimize arbitrary user-supplied SVG files.

## Reproducible comparison

Run the fidelity integration tests with VTracer and the
[resvg renderer](https://resvg-py.readthedocs.io/en/latest/):

```bash
python -m pip install -e '.[dev,vectorize]' 'resvg-py>=0.5,<0.6'
pytest tests/test_optimization.py
```

The vectorize CI job runs these tests. Three deterministic 64x64 fixtures are
created with Pillow: a square icon, overlapping coloured logo shapes, and a
multicolour illustration. Both versions are rendered to PNG with resvg; the PNG
bytes must match exactly. XML-level tests also preserve gradients, alpha,
transforms, viewBox, and significant text; failure tests protect existing files.

Measured with VTracer 0.6.15 and resvg-py 0.5.0:

| Fixture | Original SVG bytes | Compacted bytes | Reduction | Render difference |
| --- | ---: | ---: | ---: | --- |
| Icon | 709 | 685 | 3.39% | Identical PNG bytes |
| Logo | 3537 | 3483 | 1.53% | Identical PNG bytes |
| Illustration | 1064 | 1043 | 1.97% | Identical PNG bytes |

These small fixtures demonstrate fidelity, not a universal compression ratio.
Most large output size comes from tracing detail; compaction leaves that detail
unchanged. The default remains off and no GUI setting is required for this
limited advanced option.
