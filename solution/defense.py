"""
Your defense. Implement register(ctx) and a handler per event type.
See ../README.md for the full interface + toolkit reference, and
../RULES.md before you start.
"""
from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def should_check(cost, ctx):
    return True


def check_data_batch(payload, ctx):
    res = ctx.tools.batch_profile(payload["batch_id"])
    if "error" in res:
        return Verdict(alert=False, pillar="checks")
        
    alert = False
    reasons = []
    
    # 1. Static bounds
    if res["row_count"] < ctx.baseline["row_count_min"] or res["row_count"] > ctx.baseline["row_count_max"]:
        alert = True
        reasons.append("row_count")
        
    if res["staleness_min"] > ctx.baseline["staleness_min_max"]:
        alert = True
        reasons.append("staleness")
        
    if res["mean_amount"] < ctx.baseline["mean_amount_min"] or res["mean_amount"] > ctx.baseline["mean_amount_max"]:
        alert = True
        reasons.append("mean_amount")
        
    for k, v in res["null_rate"].items():
        if v > ctx.baseline["null_rate_max"]:
            alert = True
            reasons.append(f"null_rate_{k}")
            
    # 2. Dynamic tracking
    state = ctx.state.setdefault("data_batch_stats", {
        "row_count": [],
        "mean_amount": [],
        "null_rates": {}
    })
    
    state["row_count"].append(res["row_count"])
    state["mean_amount"].append(res["mean_amount"])
    
    baseline_mean_rc = (ctx.baseline["row_count_max"] + ctx.baseline["row_count_min"]) / 2.0
    global_std_rc = (ctx.baseline["row_count_max"] - ctx.baseline["row_count_min"]) / 6.0
    
    if len(state["row_count"]) >= 3:
        mean_3 = sum(state["row_count"][-3:]) / 3.0
        if abs(mean_3 - baseline_mean_rc) > 3.0 * global_std_rc / (3 ** 0.5):
            alert = True
            reasons.append("row_count_shift")
            
    baseline_mean_amt = (ctx.baseline["mean_amount_max"] + ctx.baseline["mean_amount_min"]) / 2.0
    global_std_amt = (ctx.baseline["mean_amount_max"] - ctx.baseline["mean_amount_min"]) / 6.0
    
    if len(state["mean_amount"]) >= 3:
        mean_3 = sum(state["mean_amount"][-3:]) / 3.0
        if mean_3 > baseline_mean_amt + 2.0 * global_std_amt / (3 ** 0.5) or mean_3 < baseline_mean_amt - 2.0 * global_std_amt / (3 ** 0.5):
            alert = True
            reasons.append("mean_amount_shift")
            
    return Verdict(alert=alert, reason=",".join(reasons), pillar="checks")


def check_contract_checkpoint(payload, ctx):
    if not should_check(1.5, ctx):
        return Verdict(alert=False, pillar="contracts")
        
    res = ctx.tools.contract_diff(payload["contract_id"], payload["checkpoint_batch_id"])
    if "error" in res:
        # If it's a real schema error, maybe alert?
        if "schema" in res["error"].lower() or "missing" in res["error"].lower():
            return Verdict(alert=True, reason="schema_break", pillar="contracts")
        return Verdict(alert=False, reason=res["error"], pillar="contracts")
        
    alert = False
    reasons = []
    
    if res["freshness_delay_min"] > ctx.baseline["freshness_delay_max_min"]:
        alert = True
        reasons.append("freshness")
    if len(res.get("violations", [])) > 0:
        alert = True
        reasons.append("violations")
        
    if not alert:
        return Verdict(alert=False, reason=f"UNKNOWN_TYPE:{payload.get('type')}", pillar="contracts")
        
    return Verdict(alert=alert, reason=",".join(reasons), pillar="contracts")


def check_lineage_run(payload, ctx):
    res = ctx.tools.lineage_graph_slice(payload["run_id"])
    
    if "error" in res:
        return Verdict(alert=False, pillar="lineage")
        
    alert = False
    reasons = []
    
    if res["duration_ms"] > ctx.baseline["lineage_duration_ms_max"]:
        alert = True
        reasons.append("duration")
        
    job = payload.get("job", "unknown")
    state_key = f"lineage_upstreams_{job}"
    current_upstreams = set(res["actual_upstream"])
    
    if state_key not in ctx.state:
        ctx.state[state_key] = current_upstreams
    else:
        expected = ctx.state[state_key]
        if expected and len(current_upstreams) < len(expected):
            alert = True
            reasons.append("missing_upstream")
        ctx.state[state_key].update(current_upstreams)
        
    if res["actual_downstream_count"] == 0:
        alert = True
        reasons.append("orphaned_output")
        
    return Verdict(alert=alert, reason=",".join(reasons), pillar="lineage")


def check_feature_materialization(payload, ctx):
    if not should_check(2.0, ctx):
        return Verdict(alert=False, pillar="ai_infra")
        
    res = ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    if "error" in res:
        return Verdict(alert=False, pillar="ai_infra")
        
    alert = False
    reasons = []
    
    if res["mean_shift_sigma"] > ctx.baseline["feature_mean_shift_sigma_max"] * 1.1:
        alert = True
        reasons.append("mean_shift")
        
    return Verdict(alert=alert, reason=",".join(reasons), pillar="ai_infra")


def check_embedding_batch(payload, ctx):
    if not should_check(2.0, ctx):
        return Verdict(alert=False, pillar="ai_infra")
        
    res = ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    if "error" in res:
        return Verdict(alert=False, pillar="ai_infra")
        
    alert = False
    reasons = []
    
    state = ctx.state.setdefault("embedding", {"doc_age": [], "centroid": []})
    
    if res["centroid_shift"] > ctx.baseline["embedding_centroid_shift_max"]:
        alert = True
        reasons.append("centroid_shift")
        
    if res["avg_doc_age_days"] > ctx.baseline["corpus_avg_doc_age_days_max"]:
        alert = True
        reasons.append("doc_age")
        
    return Verdict(alert=alert, reason=",".join(reasons), pillar="ai_infra")
