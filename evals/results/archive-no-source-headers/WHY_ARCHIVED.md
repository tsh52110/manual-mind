Runs on the PyMuPDF corpus but with an eval-harness defect: retrieved_contexts
passed to Ragas lacked the manual-title headers the generator saw, so the judge
correctly rejected claims attributing specs to a named vehicle ('no mention of
HMMWV in the context'). Kept as the 'before' for the harness fix; see README.
