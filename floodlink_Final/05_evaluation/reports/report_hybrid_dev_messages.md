# Evaluation report — strategy: hybrid — data: dev_messages.jsonl

| metric | value |
|---|---|
| strategy | hybrid |
| messages | 39 |
| seconds | 0.2 |
| escalated_to_llm | 0 |
| failed_messages | 0 |
| message_type_accuracy | 1.0 |
| priority_accuracy | 1.0 |
| red_recall | 1.0 |
| flags_f1 | 1.0 |
| needs_f1 | 1.0 |
| missing_fields_exact | 1.0 |
| duplicate_precision | 0.0 |
| duplicate_recall | 0.0 |
| resolved_closed | 1/2 |

## Field accuracy

| field | accuracy |
|---|---|
| area | 1.0 |
| adults | 0.929 |
| water_level | 1.0 |
| children_ages | 1.0 |
| elderly_ages | 1.0 |

## Priority confusion (rows = gold, cols = predicted)

| gold \ pred | red | orange | yellow | green |
|---|---|---|---|---|
| red | 11 | 0 | 0 | 0 |
| orange | 0 | 12 | 0 | 0 |
| yellow | 0 | 0 | 2 | 0 |
| green | 0 | 0 | 0 | 3 |