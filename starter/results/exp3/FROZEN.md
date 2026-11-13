# Frozen before test run
Frozen at: 2026-11-13T07:47:51Z (UTC). Test split had NOT been run at this time.

Selection criterion (defined before reading any test result): highest Evidence Hit@3 on dev,
then highest Hit@1 on dev, then fewer chunks / lower resource use.

Dev (exp1-exp3): A 6/15 & 10/15; A2 6/15 & 10/15; B 8/15 & 11/15; B2 8/15 & 11/15; C 8/15 & 12/15; C2 8/15 & 12/15.
Selected configuration: **C2** = B2 chunks (heading/paragraph, max 1200 chars, fragments <30 chars dropped) + ip_type filter on filter questions.
Test is run once for ALL six strategies for the comparison tables; no parameter may change after this point.
Changes made after exp1 and before this freeze: header cleaning variant A2 (exp2), fragment drop B2/C2 (exp3). Both evaluated on dev only.
