# Evaluation report — strategy: rules — data: hard_messages.jsonl

| metric | value |
|---|---|
| strategy | rules |
| messages | 30 |
| seconds | 0.0 |
| escalated_to_llm | 0 |
| failed_messages | 0 |
| message_type_accuracy | 0.667 |
| priority_accuracy | 0.368 |
| red_recall | 0.556 |
| flags_f1 | 0.615 |
| needs_f1 | 0.522 |
| missing_fields_exact | 0.316 |
| duplicate_precision | 0.0 |
| duplicate_recall | 0.0 |
| resolved_closed | 0/1 |

## Field accuracy

| field | accuracy |
|---|---|
| area | 1.0 |
| adults | 0.308 |
| water_level | 0.588 |
| children_ages | 0.789 |
| elderly_ages | 0.842 |

## Priority confusion (rows = gold, cols = predicted)

| gold \ pred | red | orange | yellow | green |
|---|---|---|---|---|
| red | 5 | 1 | 1 | 2 |
| orange | 0 | 1 | 4 | 3 |
| yellow | 0 | 0 | 1 | 0 |
| green | 0 | 0 | 1 | 0 |