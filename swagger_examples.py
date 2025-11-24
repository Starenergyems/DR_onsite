DAY_SELECT_CBL_RESPONSE_EXAMPLE = {
    "customer_id": "C001",
    "event_start": "2025-07-01T16:00:00+08:00",
    "event_end": "2025-07-01T22:00:00+08:00",
    "cbl_kw": 99.9,
    "baseline_source_days": ["2025-06-03", "2025-06-04", "2025-06-05", "2025-06-06", "2025-06-09"],
    "method": "day-select-cbl-v1",
    "detail": {
        "cbl1_kw": 98.7,
        "af_kw": 1.2,
        "cbl1_plus_af_kw": 99.9,
        "cbl2_kw": 120.0,
        "cbl_kw": 99.9,
        "hist_adjust_avg_kw": 97.5,
        "today_adjust_avg_kw": 99.0,
        "assumed_today_adjust_avg_kw": 95.0,
    },
}

DAY_SELECT_REWARD_RESPONSE_EXAMPLE = {
    "customer_id": "C001",
    "event_start": "2025-07-01T16:00:00+08:00",
    "event_end": "2025-07-01T22:00:00+08:00",
    "committed_capacity_kw": 100.0,
    "cbl_kw": 99.9,
    "actual_avg_kw": 85.0,
    "actual_reduction_kw": 14.9,
    "execution_rate": 0.9,
    "reduction_ratio": 1.0,
    "tariff_rate": 1.84,
    "event_duration_hours": 6.0,
    "reward_ntd": 2462.4,
    "baseline_source_days": ["2025-06-03", "2025-06-04", "2025-06-05", "2025-06-06", "2025-06-09"],
    "method": "day-select-reward-v1",
    "detail": {
        "cbl1_kw": 98.7,
        "af_kw": 1.2,
        "cbl1_plus_af_kw": 99.9,
        "cbl2_kw": 120.0,
        "cbl_kw": 99.9,
        "hist_adjust_avg_kw": 97.5,
        "today_adjust_avg_kw": 99.0,
        "actual_avg_kw": 85.0,
        "actual_reduction_kw": 14.9,
        "execution_rate_ratio": 0.9,
        "reduction_ratio": 1.0,
        "tariff_rate": 1.84,
        "event_duration_hours": 6.0,
        "reward_ntd": 2462.4,
    },
}

DAY_SELECT_REDUCTION_RESPONSE_EXAMPLE = {
    "customer_id": "C001",
    "event_start": "2025-07-01T16:00:00+08:00",
    "event_end": "2025-07-01T22:00:00+08:00",
    "cbl_kw": 99.9,
    "actual_avg_kw": 85.0,
    "actual_reduction_kw": 14.9,
    "committed_capacity_kw": 100.0,
    "execution_rate": 0.9,
    "reduction_ratio": 1.0,
    "baseline_source_days": ["2025-06-03", "2025-06-04", "2025-06-05", "2025-06-06", "2025-06-09"],
    "method": "day-select-reduction-v1",
    "detail": {
        "cbl1_kw": 98.7,
        "af_kw": 1.2,
        "cbl1_plus_af_kw": 99.9,
        "cbl2_kw": 120.0,
        "cbl_kw": 99.9,
        "hist_adjust_avg_kw": 97.5,
        "today_adjust_avg_kw": 99.0,
        "actual_avg_kw": 85.0,
        "actual_reduction_kw": 14.9,
        "execution_rate": 0.9,
        "reduction_ratio": 1.0,
    },
}

GUARANTEED_CBL_RESPONSE_EXAMPLE = {
    "customer_id": "G001",
    "event_start": "2025-08-01T13:00:00+08:00",
    "notification_minutes_before": 60,
    "baseline_kw": 100.0,
    "detail": {
        "baseline_start": "2025-08-01T11:00:00+08:00",
        "baseline_end": "2025-08-01T13:00:00+08:00",
        "baseline_kw": 100.0,
    },
}

GUARANTEED_EVENT_RESPONSE_EXAMPLE = {
    "customer_id": "G001",
    "event_start": "2025-08-01T13:00:00+08:00",
    "event_end": "2025-08-01T16:00:00+08:00",
    "baseline_kw": 100.0,
    "actual_reduction_kw": 20.0,
    "execution_rate": 0.2,
    "event_duration_hours": 3.0,
    "flow_reduction_amount": 0.0,
    "extra_charge_amount": 5760.0,
    "detail": {
        "baseline_start": "2025-08-01T11:00:00+08:00",
        "baseline_end": "2025-08-01T13:00:00+08:00",
        "baseline_kw": 100.0,
        "actual_avg_kw": 80.0,
        "actual_reduction_kw": 20.0,
        "execution_rate": 0.2,
        "capacity_denom_kw": 100.0,
        "committed_capacity_kw": 100.0,
        "event_duration_hours": 3.0,
        "flow_fee_rate": 12.0,
        "flow_reduction_amount": 0.0,
        "extra_charge_amount": 5760.0,
    },
}

GUARANTEED_REWARD_RESPONSE_EXAMPLE = {
    "customer_id": "G001",
    "contract_capacity_kw": 100.0,
    "average_execution_rate": 0.8,
    "reduction_ratio": 0.6,
    "basic_fee_rate": 84.0,
    "flow_fee_rate": 12.0,
    "basic_reduction_amount": 5040.0,
    "flow_reduction_total_amount": 1680.0,
    "extra_charge_total_amount": 0.0,
    "net_reward_amount": 6720.0,
    "event_details": [
        {
            "event_start": "2025-08-01T13:00:00+08:00",
            "event_end": "2025-08-01T16:00:00+08:00",
            "baseline_kw": 100.0,
            "actual_avg_kw": 30.0,
            "actual_reduction_kw": 70.0,
            "execution_rate": 0.8,
            "event_duration_hours": 3.0,
            "flow_reduction_amount": 1680.0,
            "extra_charge_amount": 0.0,
            "detail": {
                "baseline_start": "2025-08-01T11:00:00+08:00",
                "baseline_end": "2025-08-01T13:00:00+08:00",
                "baseline_kw": 100.0,
                "actual_avg_kw": 30.0,
                "actual_reduction_kw": 70.0,
                "execution_rate": 0.8,
                "capacity_denom_kw": 90.0,
                "committed_capacity_kw": 90.0,
                "event_duration_hours": 3.0,
                "flow_fee_rate": 12.0,
                "flow_reduction_amount": 1680.0,
                "extra_charge_amount": 0.0,
            },
        }
    ],
}

DAY_SELECT_CBL_ERROR_EXAMPLE = {
    "detail": "基準日 2025-06-30 22:00-24:00 缺少 8 筆 15 分鐘區間，例: 2025-06-30T22:00:00+08:00"
}

DAY_SELECT_REWARD_ERROR_EXAMPLE = {
    "detail": "日選型最低約定抑低契約容量須達 20 瓩"
}

DAY_SELECT_REDUCTION_ERROR_EXAMPLE = {
    "detail": "日選型經常契約容量須達 100 瓩以上"
}

GUARANTEED_CBL_ERROR_EXAMPLE = {
    "detail": "事件日期須為工作日且非離峰日"
}

GUARANTEED_EVENT_ERROR_EXAMPLE = {
    "detail": "約定抑低契約容量須達 1,000 瓩或經常契約容量的 15% 以上 (最低 1500.0 瓩)"
}

GUARANTEED_REWARD_ERROR_EXAMPLE = GUARANTEED_EVENT_ERROR_EXAMPLE
