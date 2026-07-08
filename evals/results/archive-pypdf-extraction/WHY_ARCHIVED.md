Ragas runs against indexes built with raw pypdf extraction, which left broken
kerning in spec tables ('15 0  horsepower', 'p s i'). The judge correctly marked
answers unsupported by that corrupted text, depressing faithfulness (baseline
0.594). Kept as the 'before' evidence for the extraction fix; see README.
