# Results (gemini-3.5-flash-lite, budget 8 calls / 8000 output tokens)

| name             |   bugs |   attempts |   correct_rate |   ci95_low |   ci95_high |   plausible_incorrect_rate |   overfitting_rate |   mean_calls |   mean_output_tokens |   any_hallucination |
|:-----------------|-------:|-----------:|---------------:|-----------:|------------:|---------------------------:|-------------------:|-------------:|---------------------:|--------------------:|
| S0 single-shot   |     31 |         93 |          0.968 |      0.903 |       1.000 |                      0.032 |              0.032 |        1.000 |              107.323 |               0.000 |
| S1 single agent  |     31 |         93 |          0.968 |      0.903 |       1.000 |                      0.032 |              0.032 |        1.000 |              105.946 |               0.000 |
| S2 multi-agent   |     31 |         93 |          0.957 |      0.892 |       1.000 |                      0.022 |              0.022 |        3.763 |              341.161 |               0.022 |
| S2-R no reviewer |     31 |         93 |          0.946 |      0.860 |       1.000 |                      0.032 |              0.033 |        2.194 |              197.914 |               0.000 |

## McNemar (exact, paired by bug and run)

| a   | b   |   pairs |   only_a_correct |   only_b_correct |   p_value_exact |
|:----|:----|--------:|-----------------:|-----------------:|----------------:|
| s1  | s2  |      93 |                2 |                1 |          1.0000 |
| s2  | s2r |      93 |                1 |                0 |          1.0000 |
| s1  | s2r |      93 |                2 |                0 |          0.5000 |
| s0  | s1  |      93 |                0 |                0 |          1.0000 |
| s0  | s2  |      93 |                2 |                1 |          1.0000 |
