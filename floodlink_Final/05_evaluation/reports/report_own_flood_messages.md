# Evaluation report — strategy: own — data: flood_messages.jsonl

| metric | value |
|---|---|
| strategy | own |
| messages | 200 |
| seconds | 1.8 |
| escalated_to_llm | 0 |
| failed_messages | 0 |
| message_type_accuracy | 0.995 |
| priority_accuracy | 0.967 |
| red_recall | 0.931 |
| flags_f1 | 0.987 |
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
| red | 27 | 1 | 1 | 0 |
| orange | 0 | 72 | 1 | 2 |
| yellow | 0 | 0 | 29 | 0 |
| green | 0 | 0 | 0 | 17 |