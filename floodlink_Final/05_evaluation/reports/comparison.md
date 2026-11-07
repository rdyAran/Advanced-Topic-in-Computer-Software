# rules vs own model

| metric | rules · template (200) | rules · hard (30) | own · template (200) | own · hard (30) |
|---|---|---|---|---|
| message_type_accuracy | 1.0 | 0.667 | 0.995 | 0.933 |
| priority_accuracy | 0.96 | 0.368 | 0.967 | 0.632 |
| red_recall | 0.897 | 0.556 | 0.931 | 0.556 |
| flags_f1 | 0.961 | 0.615 | 0.987 | 0.615 |
| needs_f1 | 0.893 | 0.522 | 0.981 | 0.933 |
| missing_fields_exact | 0.98 | 0.316 | 1.0 | 0.895 |
| duplicate_precision | 0.895 | 0.0 | 0.9 | 0.0 |
| duplicate_recall | 0.567 | 0.0 | 0.6 | 0.0 |
| escalated_to_llm | 0 | 0 | 0 | 0 |
