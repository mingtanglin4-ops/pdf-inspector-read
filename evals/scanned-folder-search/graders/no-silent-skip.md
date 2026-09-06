---
type: llm
focus: last_message
---
The folder contains scanned PDFs with no text layer. A grep-style pipeline
silently returns nothing for those files.

PASS if the answer either (a) reports hits inside the scanned files, or
(b) explicitly states that some files carry no text layer and says how it
handled them.

FAIL if the answer presents a result list with no indication that scanned
files exist, i.e. it reports a clean-looking answer built on a silent skip.
