# Evaluation report — strategy: rules — data: flood_messages.jsonl

| metric | value |
|---|---|
| strategy | rules |
| messages | 200 |
| seconds | 0.6 |
| escalated_to_llm | 0 |
| failed_messages | 0 |
| message_type_accuracy | 1.0 |
| priority_accuracy | 0.96 |
| red_recall | 0.897 |
| flags_f1 | 0.961 |
| needs_f1 | 0.893 |
| missing_fields_exact | 0.98 |
| duplicate_precision | 0.895 |
| duplicate_recall | 0.567 |
| resolved_closed | 5/6 |

## Field accuracy

| field | accuracy |
|---|---|
| area | 0.973 |
| adults | 0.967 |
| water_level | 0.92 |
| children_ages | 0.98 |
| elderly_ages | 0.987 |

## Priority confusion (rows = gold, cols = predicted)

| gold \ pred | red | orange | yellow | green |
|---|---|---|---|---|
| red | 26 | 1 | 1 | 1 |
| orange | 0 | 72 | 1 | 2 |
| yellow | 0 | 0 | 29 | 0 |
| green | 0 | 0 | 0 | 17 |