# Reflection (≤1 page)

**Which fault types were hardest to catch, and why?**
The subtle data distribution shifts (e.g., within the `checks` and `ai_infra` pillars) were the hardest to catch. The provided baseline thresholds (`mean ± 3σ`) only flag obvious anomalies. Subtle faults fall inside this wide 6-sigma band. To catch them, one needs to maintain a running mean and variance in `ctx.state` and look for sudden shifts relative to recent history, rather than just relying on the static global bounds. 

**What would you change about your cost/coverage tradeoff, if you had another pass?**
If I had another pass, I would implement a dynamic budget allocator. Currently, the agent checks every single event since the cost overage penalty is much smaller than the reward for catching a fault. However, for a much longer stream, this would result in a massive cost overage. A better approach would be to randomly sample events for expensive checks (like `feature_drift`), or only trigger them when upstream data volume/null-rate anomalies already raise suspicion, thereby preserving budget while maintaining high coverage.
