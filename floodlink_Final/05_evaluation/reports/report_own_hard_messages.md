# Evaluation report — strategy: own — data: hard_messages.jsonl

| metric | value |
|---|---|
| strategy | own |
| messages | 30 |
| seconds | 0.1 |
| escalated_to_llm | 0 |
| failed_messages | 0 |
| message_type_accuracy | 0.933 |
| priority_accuracy | 0.632 |
| red_recall | 0.556 |
| flags_f1 | 0.615 |
| needs_f1 | 0.933 |
| missing_fields_exact | 0.895 |
| duplicate_precision | 0.0 |
| duplicate_recall | 0.0 |
| resolved_closed | 0/1 |

## Field accuracy

| field | accuracy |
|---|---|
| area | 1.0 |
| adults | 0.923 |
| water_level | 0.882 |
| children_ages | 0.895 |
| elderly_ages | 1.0 |

## Priority confusion (rows = gold, cols = predicted)

| gold \ pred | red | orange | yellow | green |
|---|---|---|---|---|
| red | 5 | 2 | 0 | 2 |
| orange | 0 | 5 | 2 | 1 |
| yellow | 0 | 0 | 1 | 0 |
| green | 0 | 0 | 0 | 1 |