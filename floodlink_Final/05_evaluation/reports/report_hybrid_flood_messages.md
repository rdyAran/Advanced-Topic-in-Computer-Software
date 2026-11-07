# Evaluation report — strategy: hybrid — data: flood_messages.jsonl

| metric | value |
|---|---|
| strategy | hybrid |
| messages | 200 |
| seconds | 1.9 |
| escalated_to_llm | 1 |
| failed_messages | 0 |
| message_type_accuracy | 0.995 |
| priority_accuracy | 0.96 |
| red_recall | 0.897 |
| flags_f1 | 0.961 |
| needs_f1 | 0.981 |
| missing_fields_exact | 1.0 |
| duplicate_precision | 0.9 |
| duplicate_recall | 0.6 |
| resolved_closed | 4/6 |

## Field accuracy

| field | accuracy |
|---|---|
| area | 0.973 |
| adults | 0.967 |
| water_level | 0.933 |
| children_ages | 0.987 |
| elderly_ages | 0.993 |

## Priority confusion (rows = gold, cols = predicted)

| gold \ pred | red | orange | yellow | green |
|---|---|---|---|---|
| red | 26 | 1 | 1 | 1 |
| orange | 0 | 72 | 1 | 2 |
| yellow | 0 | 0 | 29 | 0 |
| green | 0 | 0 | 0 | 17 |