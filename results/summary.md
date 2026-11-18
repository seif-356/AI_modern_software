# Results (gemini-3.5-flash-lite, budget 8 calls / 8000 output tokens)

| name             |   bugs |   attempts |   correct_rate |   ci95_low |   ci95_high |   plausible_incorrect_rate |   overfitting_rate |   mean_calls |   mean_output_tokens |   any_hallucination |
|:-----------------|-------:|-----------:|---------------:|-----------:|------------:|---------------------------:|-------------------:|-------------:|---------------------:|--------------------:|
| S0 single-shot   |     31 |         57 |          0.965 |      0.903 |       1.000 |                      0.035 |              0.035 |        1.000 |              109.614 |               0.000 |
| S1 single agent  |     31 |         58 |          0.966 |      0.903 |       1.000 |                      0.034 |              0.034 |        1.000 |              106.362 |               0.000 |
| S2 multi-agent   |     31 |         56 |          0.982 |      0.952 |       1.000 |                      0.018 |              0.018 |        3.786 |              355.339 |               0.018 |
| S2-R no reviewer |     31 |         57 |          0.965 |      0.903 |       1.000 |                      0.035 |              0.035 |        2.105 |              189.351 |               0.000 |

## McNemar (exact, paired by bug and run)

| a   | b   |   pairs |   only_a_correct |   only_b_correct |   p_value_exact |
|:----|:----|--------:|-----------------:|-----------------:|----------------:|
| s1  | s2  |      56 |                0 |                1 |          1.0000 |
| s2  | s2r |      56 |                1 |                0 |          1.0000 |
| s1  | s2r |      57 |                0 |                0 |          1.0000 |
| s0  | s1  |      57 |                0 |                0 |          1.0000 |
| s0  | s2  |      56 |                0 |                1 |          1.0000 |
