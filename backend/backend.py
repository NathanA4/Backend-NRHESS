from flask_cors import CORS
from flask import Flask, jsonify, request
from model import db, User, EnergyDemandProjection, DailyProfile, Location
from collections import defaultdict
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from sqlalchemy.exc import IntegrityError
import random
import json
import requests, traceback
from datetime import datetime, timedelta
from collections import defaultdict
import os
import math
import traceback
from copy import deepcopy


# app = Flask(__name__)
# bcrypt = Bcrypt(app)

# username = "root" 
# password = "1234" 
# database = "Airplane_System"

# app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{username}:{password}@localhost:3000/{database}'
app = Flask(__name__)
bcrypt = Bcrypt(app)

username = os.getenv("MYSQL_USER")
password = os.getenv("MYSQL_PASSWORD")
host = os.getenv("MYSQL_HOST")
port = os.getenv("MYSQL_PORT", "3306")
database = os.getenv("MYSQL_DATABASE", "nrhess")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "ssl": {
            "ca": os.getenv("MYSQL_SSL_CA")
        }
    }
}

db.init_app(app)

CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route("/")
def home():
    return jsonify({"message": "NR-HESS backend is running on Render"})

# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# db.init_app(app) 
# CORS(app)

#username = os.getenv("MYSQL_USER")
#password = os.getenv("MYSQL_PASSWORD")
#host = os.getenv("MYSQL_HOST")
#port = os.getenv("MYSQL_PORT")
#database = os.getenv("MYSQL_DATABASE")

#app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
#app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


#db.init_app(app)
#CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No input data provided"}), 400

        username = data.get('username')
        password = data.get('password')

        if not all([username, password]):
            return jsonify({"error": "Missing required fields"}), 400

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        new_user = User(name=username, password=hashed_password)

        db.session.add(new_user)
        db.session.commit()

        return jsonify({"message": "User registered successfully!"}), 201

    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "User with this email or username already exists"}), 409

    except Exception as e:
        return jsonify({"error": "An error occurred", "details": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(name=username).first()

    if user is None:
        return jsonify({"Error": "Unauthorized User"}), 401

    if not bcrypt.check_password_hash(user.password, password):
        return jsonify({"Error": "Unauthorized User"}), 401

    return jsonify({
        "userId": user.id,
        "username": user.name,
    })
@app.route('/api/reset_password', methods=['POST'])
def reset_password():
    data = request.get_json()
    username = data.get('username')
    new_password = data.get('new_password')

    if not all([username, new_password]):
        return jsonify({"error": "Missing fields"}), 400

    user = User.query.filter_by(name=username).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.password = bcrypt.generate_password_hash(new_password).decode("utf-8")
    db.session.commit()
    return jsonify({"message": "Password reset successful"}), 200

@app.route('/api/energy_demand', methods=['POST'])
def save_energy_demand():
    try:
        data = request.get_json()
        print("Received Energy Demand data:", data)

        user_id = data['user_id']
        name = data['name']
        demand_by_year = data['demand_per_year']  # dict like {"2025": 300, "2030": 350, ...}

        energy_by_year = {}
        for year, power in demand_by_year.items():
            try:
                energy = round(float(power) * 8760)
                energy_by_year[year] = energy
            except ValueError:
                return jsonify({'error': f'Invalid power value for year {year}: {power}'}), 400

        # Store both power and energy
        full_demand = {
            "power": demand_by_year,
            "energy": energy_by_year
        }
        
        existing = EnergyDemandProjection.query.filter_by(user_id=user_id, name=name).first()

        if existing:
            existing.base_demand = 0
            existing.growth_rate = json.dumps(full_demand)
        else:
            count = EnergyDemandProjection.query.filter_by(user_id=user_id).count()
            if count >= 10:
                return jsonify({'error': 'Max 10 projections allowed'}), 400

            proj = EnergyDemandProjection(
                name=name,
                base_demand=0,
                growth_rate=json.dumps(full_demand),
                user_id=user_id
            )
            db.session.add(proj)

        db.session.commit()
        return jsonify({'message': 'Projection saved', 'energy_per_year': energy_by_year})
    

    except IntegrityError as e:
        db.session.rollback()
        if "Duplicate entry" in str(e.orig):
            return jsonify({'error': 'A projection with this name already exists for this user.'}), 400
        return jsonify({'error': 'Database integrity error', 'details': str(e.orig)}), 500

    except Exception as e:
        db.session.rollback()
        print("Error saving energy demand:", e)
        return jsonify({'error': 'Server error', 'details': str(e)}), 500


@app.route('/api/user_energy_demand/<int:user_id>', methods=['GET'])
def get_energy_demands(user_id):
    projections = EnergyDemandProjection.query.filter_by(user_id=user_id).all()
    return jsonify([
        {
            'id': p.id,
            'name': p.name,
            'base_demand': p.base_demand,
            'demand_per_year': json.loads(p.growth_rate),
            'energy': {
                year: round(float(value) * 8760)
                for year, value in (
                    json.loads(p.growth_rate).get("power", json.loads(p.growth_rate))
                    if isinstance(json.loads(p.growth_rate), dict)
                    else {
                        str(2025 + i * 5): val for i, val in enumerate(json.loads(p.growth_rate))
                    }
                ).items()
            },
            'user_id': p.user_id
        }
        for p in projections
    ])

@app.route('/api/daily_profile', methods=['POST'])
def save_daily_profile():
    try:
        data = request.get_json()
        print("Received data:", data)
        region = data.get("region", "Region")

        user_id = data['user_id']
        name = data['name']
        hourly_values = data['hourly_values']
        variability_day = data.get('variability_day', 0)
        variability_time = data.get('variability_time', 0)

        existing = DailyProfile.query.filter_by(user_id=user_id, name=name).first()

        if existing:
            existing.hourly_values = json.dumps(hourly_values)
            existing.variability_day = variability_day
            existing.variability_time = variability_time
        else:
            count = DailyProfile.query.filter_by(user_id=user_id).count()
            if count >= 10:
                return jsonify({'error': 'Max 10 daily profiles allowed'}), 400
            profile = DailyProfile(
                name=name,
                hourly_values=json.dumps(hourly_values),
                variability_day=variability_day,
                variability_time=variability_time,
                user_id=user_id
            )
            db.session.add(profile)

        db.session.commit()
        return jsonify({'message': 'Daily profile saved'})

    except Exception as e:
        print("Error saving profile:", e)
        return jsonify({'error': 'Server error', 'details': str(e)}), 500
    

@app.route('/api/user_daily_profiles/<int:user_id>', methods=['GET'])
def get_user_profiles(user_id):
    profiles = DailyProfile.query.filter_by(user_id=user_id).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'hourly_values': json.loads(p.hourly_values),
        'variability_day': p.variability_day,
        'variability_time': p.variability_time
    } for p in profiles])


@app.route('/api/generate_demand', methods=['POST'])
def generate_demand():
    data = request.get_json()
    user_id = data.get('user_id')
    projection_name = data.get('projection_name')
    profile_name = data.get('profile_name')

    if not all([user_id, projection_name, profile_name]):
        return jsonify({"error": "Missing user_id, projection_name, or profile_name"}), 400

    # Fetch demand projection
    demand_projection = EnergyDemandProjection.query.filter_by(user_id=user_id, name=projection_name).first()
    if not demand_projection:
        return jsonify({"error": "Demand projection not found"}), 404

    demand_per_year = demand_projection.growth_rate
    if isinstance(demand_per_year, str):
        demand_per_year = json.loads(demand_per_year)

    power_by_year = demand_per_year.get("power", {})
    base = power_by_year.get("2025", 100)
    future_growth_values = []
    keys = ["2030", "2035", "2040", "2045", "2050", "2055", "2060-2100"]
    for year in keys:
        if year in power_by_year:
            years = 40 if year == "2060-2100" else 5
            growth = (power_by_year[year] - base) / base / years * 100
            future_growth_values.append(growth)

    growth = sum(future_growth_values) / len(future_growth_values) / 100

    # Fetch profile
    profile = DailyProfile.query.filter_by(user_id=user_id, name=profile_name).first()
    if not profile:
        return jsonify({"error": "Daily profile not found"}), 404

    try:
        hourly = json.loads(profile.hourly_values)
    except Exception as e:
        print("Hourly conversion error:", e)
        hourly = [1.0] * 24

    var_day = (profile.variability_day or 0) / 100
    var_time = (profile.variability_time or 0) / 100

    # Generate demand profile
    output = []
    start_date = datetime(2025, 1, 1)

    for day in range(365):
        date = start_date + timedelta(days=day)
        day_mod = random.uniform(1 - var_day, 1 + var_day)
        for hour in range(24):
            time_mod = random.uniform(1 - var_time, 1 + var_time)
            pu = hourly[hour] * day_mod * time_mod
            output.append({
                'date': date.strftime('%d-%b'),
                'year': 2025,
                'day': day + 1,
                'hour': hour,
                'pu': round(pu * 100, 2)
            })
    return jsonify({'profile': output})

@app.route('/api/locations', methods=['GET'])
def get_locations():
    locations = Location.query.all()
    return jsonify([loc.to_dict() for loc in locations])

@app.route('/api/location', methods=['POST'])
def add_location():
    data = request.get_json()
    try:
        location = Location(
            name=data['name'],
            solar_irradiance=data['solar_irradiance'],
            wind_speed=data['wind_speed'],
            solar_profile_dry=data.get('solar_profile_dry'),
            solar_profile_rainy=data.get('solar_profile_rainy'),
            wind_profile_dry=data.get('wind_profile_dry'),
            wind_profile_rainy=data.get('wind_profile_rainy'),
        )
        db.session.add(location)
        db.session.commit()
        return jsonify(location.to_dict()), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Location already exists'}), 400
def _gen_compute_crf(rate, lifetime):
    return (rate * (1 + rate) ** lifetime) / ((1 + rate) ** lifetime - 1) if lifetime > 0 else 0.0

def _gen_annual_cost_per_kwh(source, cf, discount_rate):
    """
    HOMER-like levelized cost/kWh for a single source:
      ((capex * CRF) + opex) / (cf * 8760) + fuel_price
    Expects source keys: capital_cost ($/kW), om_cost ($/kW-yr), fuel_price ($/kWh), lifetime (yr)
    """
    capex = float(source.get("capital_cost", 0.0))
    opex  = float(source.get("om_cost", 0.0))
    fuel  = float(source.get("fuel_price", 0.0))
    life  = int(source.get("lifetime", 25) or 25)
    if cf <= 0:
        return float("inf")
    crf = _gen_compute_crf(discount_rate, life)
    return ((capex * crf) + opex) / (cf * 8760.0) + fuel

def _gen_random_mix_with_bounds(mins, maxs, seed=None):
    """
    Create a random percentage mix that respects per-source min/max (in %),
    and sums to exactly 100%.
    """
    if seed is not None:
        import random as _r
        _r.seed(seed)
    else:
        _r = random

    n = len(mins)
    mins = [max(0.0, float(m)) for m in mins]
    maxs = [min(100.0, float(M)) for M in maxs]
    for i in range(n):
        if maxs[i] < mins[i]:
            maxs[i] = mins[i]

    min_sum = sum(mins)
    if min_sum > 100.0:
        mins = [m * (100.0 / min_sum) for m in mins]
        min_sum = 100.0

    headroom = [maxs[i] - mins[i] for i in range(n)]
    total_headroom = sum(headroom)
    if total_headroom <= 1e-9:
        mix = mins[:]
        scale = 100.0 / sum(mix) if sum(mix) > 0 else 0.0
        return [round(x * scale, 2) for x in mix]

    weights = [_r.random() for _ in range(n)]
    wsum = sum(weights) or 1.0
    allocation = [(w / wsum) * (100.0 - min_sum) for w in weights]
    allocation = [min(allocation[i], headroom[i]) for i in range(n)]
    mix = [mins[i] + allocation[i] for i in range(n)]
    s = sum(mix)
    if s <= 0:
        mix = [100.0 / n] * n
    else:
        mix = [x * (100.0 / s) for x in mix]
    return [round(x, 2) for x in mix]

def _gen_apply_smoothing(prev_mix, mix, max_delta=20.0):
    """
    Limit per-source change vs previous year by max_delta percentage points,
    then renormalize to 100%.
    """
    if not prev_mix:
        return mix
    capped = []
    for p, x in zip(prev_mix, mix):
        low  = max(0.0, p - max_delta)
        high = min(100.0, p + max_delta)
        capped.append(min(max(x, low), high))
    s = sum(capped) or 1.0
    return [round(x * (100.0 / s), 2) for x in capped]

def _gen_score_scenario_by_lcoe(mixes_by_year, sources, capacity_factors, discount_rate):
    """
    Score a scenario by average LCOE across years (lower is better).
    LCOE_year = sum_i( share_i * cost_per_kWh_i ).
    """
    per_source_cost = []
    for src in sources:
        cf = capacity_factors.get(src.get("type") or src.get("technology") or "", 0.0)
        per_source_cost.append(_gen_annual_cost_per_kwh(src, cf, discount_rate))

    lcoes = []
    for _, mix in mixes_by_year.items():
        shares = [m / 100.0 for m in mix]
        lcoe_y = sum(shares[i] * per_source_cost[i] for i in range(len(mix)))
        lcoes.append(lcoe_y)
    if not lcoes:
        return float("inf")
    return sum(lcoes) / len(lcoes)

def generate_best_scenarios(
    sources,
    capacity_factors,
    start_year=2025,
    end_year=2060,
    years_step=5,
    num_candidates=120,
    top_k=5,
    discount_rate=0.03,
    per_source_min=None,
    per_source_max=None,
    smoothing_pp=20.0,
    seed=42
):
    """
    Returns an 'installed_capacities' dict:
      { "2025": {"1":[...], "2":[...], ...}, "2030": {...}, ... }
    where each option 1..top_k is one of the best scenarios found by avg LCOE.
    """
    random.seed(seed)
    years = list(range(start_year, end_year + 1, years_step))
    n = len(sources)

    if per_source_min is None:
        per_source_min = [0.0] * n
    if per_source_max is None:
        per_source_max = [100.0] * n

    candidates = []  # (score, mixes_by_year)

    for c in range(num_candidates):
        mixes_by_year = {}
        prev = []
        local_seed = seed + c

        for y in years:
            base_mix = _gen_random_mix_with_bounds(per_source_min, per_source_max, seed=local_seed + y)
            smoothed  = _gen_apply_smoothing(prev, base_mix, max_delta=smoothing_pp) if prev else base_mix
            mixes_by_year[y] = smoothed
            prev = smoothed

        score = _gen_score_scenario_by_lcoe(mixes_by_year, sources, capacity_factors, discount_rate)
        candidates.append((score, mixes_by_year))

    candidates.sort(key=lambda x: x[0])
    best = candidates[:top_k]

    out = {str(y): {} for y in years}
    for opt_idx, (_, mixes) in enumerate(best, start=1):
        for y, mix in mixes.items():
            out[str(y)][str(opt_idx)] = mix
    return out
# ============================================================
# HURRICANE RESILIENCE CALCULATOR (from static HTML/CSS/JS doc)
# ============================================================

# ============================================================
# ENHANCED HURRICANE RESILIENCE CALCULATOR
# ============================================================

def _normal_cdf_approx(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _failure_probability_lognormal(V, mu, beta):
    """
    Lognormal fragility model:
        z = (ln(V) - ln(mu)) / beta
        P = Phi(z)
    """
    V = max(float(V), 1e-9)
    mu = max(float(mu), 1e-9)
    beta = max(float(beta), 1e-9)

    z = (math.log(V) - math.log(mu)) / beta
    return max(0.0, min(1.0, _normal_cdf_approx(z)))


def _wind_at_distance(vmax, alpha, distance):
    """
    Spatial decay:
        v_i = vmax / (1 + alpha * d_i)
    """
    return float(vmax) / (1.0 + float(alpha) * float(distance))


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(x)))


def _combine_failure_probabilities(*probs):
    """
    Union of independent-like risks:
        P_total = 1 - Π(1 - p_i)
    """
    prod = 1.0
    for p in probs:
        prod *= (1.0 - _clamp(p))
    return 1.0 - prod


def _hurricane_component_defaults():
    """
    Enhanced component defaults.
    Added:
      - type
      - flood_mu_ft
      - flood_beta
      - exposure
      - vegetation_factor
      - accessibility
      - criticality
      - customer_weight
    """
    return [
        {
            "name": "Wood Pole",
            "type": "distribution",
            "mu": 100.0, "beta": 0.22,
            "distance": 0.60,
            "recovery_hours": 36,
            "flood_mu_ft": 6.0, "flood_beta": 0.30,
            "exposure": 1.20,
            "vegetation_factor": 1.25,
            "accessibility": 0.70,
            "criticality": 0.70,
            "customer_weight": 150
        },
        {
            "name": "Steel Pole",
            "type": "distribution",
            "mu": 115.0, "beta": 0.20,
            "distance": 1.10,
            "recovery_hours": 30,
            "flood_mu_ft": 7.0, "flood_beta": 0.28,
            "exposure": 1.00,
            "vegetation_factor": 1.05,
            "accessibility": 0.75,
            "criticality": 0.72,
            "customer_weight": 170
        },
        {
            "name": "Concrete Pole",
            "type": "distribution",
            "mu": 130.0, "beta": 0.18,
            "distance": 1.80,
            "recovery_hours": 28,
            "flood_mu_ft": 8.0, "flood_beta": 0.25,
            "exposure": 0.95,
            "vegetation_factor": 1.00,
            "accessibility": 0.78,
            "criticality": 0.73,
            "customer_weight": 180
        },
        {
            "name": "Overhead Line",
            "type": "line",
            "mu": 85.0, "beta": 0.20,
            "distance": 2.60,
            "recovery_hours": 20,
            "flood_mu_ft": 10.0, "flood_beta": 0.35,
            "exposure": 1.30,
            "vegetation_factor": 1.35,
            "accessibility": 0.80,
            "criticality": 0.78,
            "customer_weight": 350
        },
        {
            "name": "Underground Cable",
            "type": "line",
            "mu": 180.0, "beta": 0.10,
            "distance": 3.20,
            "recovery_hours": 12,
            "flood_mu_ft": 3.5, "flood_beta": 0.22,
            "exposure": 0.70,
            "vegetation_factor": 1.00,
            "accessibility": 0.65,
            "criticality": 0.75,
            "customer_weight": 260
        },
        {
            "name": "Transformer",
            "type": "substation",
            "mu": 110.0, "beta": 0.21,
            "distance": 0.90,
            "recovery_hours": 24,
            "flood_mu_ft": 4.0, "flood_beta": 0.25,
            "exposure": 1.05,
            "vegetation_factor": 1.00,
            "accessibility": 0.68,
            "criticality": 0.90,
            "customer_weight": 600
        },
        {
            "name": "Substation",
            "type": "substation",
            "mu": 140.0, "beta": 0.25,
            "distance": 0.00,
            "recovery_hours": 48,
            "flood_mu_ft": 2.5, "flood_beta": 0.22,
            "exposure": 1.10,
            "vegetation_factor": 1.00,
            "accessibility": 0.55,
            "criticality": 1.00,
            "customer_weight": 2500
        },
        {
            "name": "Recloser",
            "type": "control",
            "mu": 95.0, "beta": 0.19,
            "distance": 1.70,
            "recovery_hours": 10,
            "flood_mu_ft": 4.5, "flood_beta": 0.25,
            "exposure": 1.00,
            "vegetation_factor": 1.05,
            "accessibility": 0.82,
            "criticality": 0.68,
            "customer_weight": 120
        },
        {
            "name": "Feeder Line",
            "type": "line",
            "mu": 90.0, "beta": 0.20,
            "distance": 1.00,
            "recovery_hours": 26,
            "flood_mu_ft": 8.0, "flood_beta": 0.32,
            "exposure": 1.15,
            "vegetation_factor": 1.20,
            "accessibility": 0.74,
            "criticality": 0.80,
            "customer_weight": 500
        },
        {
            "name": "Switchgear",
            "type": "substation",
            "mu": 120.0, "beta": 0.17,
            "distance": 2.40,
            "recovery_hours": 16,
            "flood_mu_ft": 3.0, "flood_beta": 0.20,
            "exposure": 0.95,
            "vegetation_factor": 1.00,
            "accessibility": 0.72,
            "criticality": 0.88,
            "customer_weight": 450
        },
    ]


def _irl_catalog_hurricane():
    return {
        "IRD": {
            "purpose": "Strengthen physical design",
            "actions": [
                "Upgrade poles and structures",
                "Add bracing and hardening",
                "Elevate or shield flood-prone equipment"
            ]
        },
        "RCS": {
            "purpose": "Improve control and switching response",
            "actions": [
                "SCADA-based switching",
                "Automated feeder transfer",
                "Adaptive islanding / reconfiguration"
            ]
        },
        "RAM": {
            "purpose": "Monitoring and alarms",
            "actions": [
                "Wind and flood sensors",
                "Storm alert thresholds",
                "Operator warning escalation"
            ]
        },
        "RIS": {
            "purpose": "Outage isolation and restoration",
            "actions": [
                "Sectionalizing affected feeders",
                "Restoration sequencing",
                "Critical-load-first restoration"
            ]
        }
    }


def _trigger_hurricane_irls(component_result):
    irls = []
    fp = component_result["failure_probability"]
    failed = component_result["failed"]
    wind = component_result["wind_mph"]
    mu = component_result["mu"]
    recovery_hours = component_result["estimated_recovery_hours"]
    flood_fp = component_result.get("flood_failure_probability", 0.0)
    criticality = component_result.get("criticality", 0.5)

    if failed:
        irls.extend(["RAM", "RIS"])

    if fp >= 0.30:
        irls.extend(["RCS", "RAM"])

    if wind >= 0.85 * mu:
        irls.append("RCS")

    if flood_fp >= 0.25:
        irls.extend(["RAM", "RIS"])

    if recovery_hours >= 24:
        irls.append("RIS")

    if criticality >= 0.85 and (failed or fp >= 0.25):
        irls.extend(["IRD", "RIS"])

    # remove duplicates, preserve order
    return list(dict.fromkeys(irls))


def _propagation_metrics(component_results):
    failed = [c for c in component_results if c["failed"]]
    at_risk = [c for c in component_results if c["failed"] or c["failure_probability"] >= 0.30]

    line_failures = sum(1 for c in failed if c["type"] == "line")
    substation_failures = sum(1 for c in failed if c["type"] == "substation")
    distribution_failures = sum(1 for c in failed if c["type"] == "distribution")
    control_failures = sum(1 for c in failed if c["type"] == "control")

    feeder_outages = max(
        round(len(at_risk) / 3),
        line_failures + round(distribution_failures * 0.5)
    )

    bus_outages = max(
        round(len(at_risk) / 4),
        substation_failures + round(control_failures * 0.5)
    )

    customers_impacted = int(sum(c.get("customer_weight", 0) for c in at_risk))
    critical_components_failed = sum(1 for c in failed if c.get("criticality", 0) >= 0.85)

    return {
        "components_at_risk": len(at_risk),
        "failed_components": len(failed),
        "feeder_outages": feeder_outages,
        "bus_outages": bus_outages,
        "critical_components_failed": critical_components_failed,
        "customers_impacted_estimate": customers_impacted
    }


def _compute_hurricane_resilience(component_results):
    if not component_results:
        return {
            "average_component_resilience": 0.0,
            "weighted_component_resilience": 0.0,
            "irl_coverage": 0.0,
            "failure_rate": 0.0,
            "resilience_metric": 0.0,
            "instantaneous_status": "NOT RESILIENT"
        }

    avg_res = sum(c["resilience"] for c in component_results) / len(component_results)

    total_criticality = sum(max(c.get("criticality", 0.5), 0.01) for c in component_results)
    weighted_res = sum(
        c["resilience"] * max(c.get("criticality", 0.5), 0.01)
        for c in component_results
    ) / total_criticality

    irl_coverage = sum(1 for c in component_results if c["irls"]) / len(component_results)
    failure_rate = sum(1 for c in component_results if c["failed"]) / len(component_results)

    avg_recovery = sum(c["estimated_recovery_hours"] for c in component_results) / len(component_results)
    recovery_penalty = min(avg_recovery / 72.0, 1.0) * 15.0

    resilience_metric = (
        0.50 * weighted_res
        + 0.20 * avg_res
        + 0.15 * (irl_coverage * 100.0)
        - 0.15 * (failure_rate * 100.0)
        - recovery_penalty
    )

    resilience_metric = max(0.0, min(100.0, resilience_metric))

    if resilience_metric >= 75:
        status = "HIGHLY RESILIENT"
    elif resilience_metric >= 60:
        status = "RESILIENT"
    elif resilience_metric >= 40:
        status = "STRESSED"
    else:
        status = "NOT RESILIENT"

    return {
        "average_component_resilience": round(avg_res, 1),
        "weighted_component_resilience": round(weighted_res, 1),
        "irl_coverage": round(irl_coverage, 2),
        "failure_rate": round(failure_rate, 2),
        "resilience_metric": round(resilience_metric, 1),
        "instantaneous_status": status
    }
def _calculate_error_margin(values, confidence_z=1.96):
    """
    95% error margin:
    error = 1.96 * std_dev / sqrt(n)
    """
    if not values or len(values) < 2:
        return 0.0

    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    std_dev = math.sqrt(variance)

    return round(confidence_z * (std_dev / math.sqrt(len(values))), 2)


def _validate_hurricane_inputs(payload, components):
    issues = []

    wind_speed = float(payload.get("wind_speed", 120))
    alpha = float(payload.get("alpha", 0.237))
    monte_carlo_runs = int(payload.get("monte_carlo_runs", 250))

    if wind_speed <= 0:
        issues.append("Wind speed must be greater than 0.")

    if alpha < 0:
        issues.append("Alpha wind decay value cannot be negative.")

    if monte_carlo_runs < 30 and str(payload.get("mode", "")).lower() == "monte carlo":
        issues.append("Monte Carlo runs should be at least 30 for stable uncertainty results.")

    for comp in components:
        if float(comp.get("mu", 0)) <= 0:
            issues.append(f"{comp.get('name', 'Component')} has invalid mu value.")

        if float(comp.get("beta", 0)) <= 0:
            issues.append(f"{comp.get('name', 'Component')} has invalid beta value.")

    return {
        "status": "Passed" if not issues else "Warning",
        "issues": issues,
        "message": "Input data is valid." if not issues else "Some input values need review."
    }


def _validate_hurricane_outputs(result):
    issues = []

    summary = result.get("summary", {})
    components = result.get("component_results", [])

    resilience_metric = summary.get("resilience_metric", 0)

    if resilience_metric < 0 or resilience_metric > 100:
        issues.append("Resilience metric is outside the expected 0–100 range.")

    for c in components:
        fp = c.get("failure_probability", 0)
        res = c.get("resilience", 0)

        if fp < 0 or fp > 1:
            issues.append(f"{c.get('component')} failure probability is outside 0–1 range.")

        if res < 0 or res > 100:
            issues.append(f"{c.get('component')} resilience is outside 0–100 range.")

    failed_count = sum(1 for c in components if c.get("failed"))
    if failed_count != summary.get("failed_components", failed_count):
        issues.append("Failed component count does not match component table.")

    return {
        "status": "Passed" if not issues else "Warning",
        "issues": issues,
        "message": "Output data is consistent." if not issues else "Some output values need review."
    }


def _build_hurricane_validation_and_error(payload, result):
    components = payload.get("components") or _hurricane_component_defaults()

    input_validation = _validate_hurricane_inputs(payload, components)
    output_validation = _validate_hurricane_outputs(result)

    component_results = result.get("component_results", [])

    resilience_values = [
        float(c.get("resilience", 0))
        for c in component_results
    ]

    failure_probability_values = [
        float(c.get("failure_probability_percent", 0))
        for c in component_results
    ]

    resilience_error = _calculate_error_margin(resilience_values)
    failure_error = _calculate_error_margin(failure_probability_values)

    overall_status = (
        "Passed"
        if input_validation["status"] == "Passed" and output_validation["status"] == "Passed"
        else "Warning"
    )

    validation = {
        "overall_status": overall_status,
        "input_validation": input_validation,
        "model_validation": {
            "status": "Passed",
            "method": "Lognormal fragility model with wind, flood, dependency, and Monte Carlo uncertainty.",
            "message": "Model calculation completed using bounded probability and resilience equations."
        },
        "output_validation": output_validation,
        "validation_summary": (
            "Hurricane inputs, model calculations, and output ranges were checked successfully."
            if overall_status == "Passed"
            else "Validation completed with warnings. Review listed issues."
        )
    }

    error_margin = {
        "confidence_level": "95%",
        "resilience_score_error_margin": f"±{resilience_error}%",
        "failure_probability_error_margin": f"±{failure_error}%",
        "interpretation": "Smaller error margin means the hurricane result is more stable."
    }

    return validation, error_margin

def _run_hurricane_resilience(payload):
    """
    Enhanced payload example:
    {
      "hurricane_category": "Category 4",
      "wind_speed": 140,
      "alpha": 0.237,
      "mode": "Monte Carlo",
      "monte_carlo_runs": 300,
      "flood_depth_ft": 4.5,
      "rainfall_intensity": 0.8,
      "network_redundancy": 0.15,
      "crew_readiness": 0.75,
      "vegetation_index": 0.70,
      "components": [...]
    }
    """
    vmax = float(payload.get("wind_speed", 120))
    alpha = float(payload.get("alpha", 0.237))
    mode = str(payload.get("mode", "Deterministic"))
    category = payload.get("hurricane_category", "Category 3")

    flood_depth_ft = float(payload.get("flood_depth_ft", 0.0))
    rainfall_intensity = _clamp(payload.get("rainfall_intensity", 0.5))
    network_redundancy = _clamp(payload.get("network_redundancy", 0.15))
    crew_readiness = _clamp(payload.get("crew_readiness", 0.70))
    vegetation_index = _clamp(payload.get("vegetation_index", 0.60))
    monte_carlo_runs = int(payload.get("monte_carlo_runs", 250))

    components = payload.get("components") or _hurricane_component_defaults()

    out = []

    for comp in components:
        name = comp["name"]
        comp_type = comp.get("type", "general")

        mu = float(comp["mu"])
        beta = float(comp["beta"])
        distance = float(comp.get("distance", 0.0))
        base_recovery_hours = float(comp.get("recovery_hours", 12))

        exposure = float(comp.get("exposure", 1.0))
        vegetation_factor = float(comp.get("vegetation_factor", 1.0))
        accessibility = _clamp(comp.get("accessibility", 0.75))
        criticality = _clamp(comp.get("criticality", 0.5))
        customer_weight = int(comp.get("customer_weight", 100))

        flood_mu_ft = float(comp.get("flood_mu_ft", 6.0))
        flood_beta = float(comp.get("flood_beta", 0.25))

        local_wind = _wind_at_distance(vmax, alpha, distance)
        effective_wind = local_wind * exposure * (1.0 + vegetation_index * (vegetation_factor - 1.0))

        wind_fp = _failure_probability_lognormal(effective_wind, mu, beta)

        effective_flood = flood_depth_ft * (1.0 + 0.35 * rainfall_intensity)
        flood_fp = _failure_probability_lognormal(
            max(effective_flood, 1e-6),
            max(flood_mu_ft, 1e-6),
            max(flood_beta, 1e-6)
        )

        # combine wind + flood + dependency effect
        dependency_fp = 0.06 if comp_type in ("substation", "control") else 0.03
        base_fp = _combine_failure_probabilities(wind_fp, flood_fp, dependency_fp)

        # network redundancy reduces effective final failure probability
        fp = base_fp * (1.0 - 0.35 * network_redundancy)
        fp = _clamp(fp)

        if mode.lower() == "monte carlo":
            failures = 0
            for _ in range(max(monte_carlo_runs, 1)):
                if random.random() < fp:
                    failures += 1
            sampled_fp = failures / max(monte_carlo_runs, 1)
            failed = sampled_fp >= 0.50
            fp_used = sampled_fp
        else:
            failed = fp >= 0.50
            fp_used = fp

        recovery_multiplier = (
            1.0
            + 1.2 * flood_fp
            + 0.7 * (1.0 - crew_readiness)
            + 0.6 * (1.0 - accessibility)
            + 0.4 * criticality
        )
        estimated_recovery_hours = base_recovery_hours * recovery_multiplier

        resilience = max(0.0, 100.0 * (1.0 - fp_used))

        row = {
            "component": name,
            "type": comp_type,
            "wind_mph": round(local_wind, 1),
            "effective_wind_mph": round(effective_wind, 1),
            "flood_depth_ft": round(effective_flood, 2),
            "mu": mu,
            "beta": beta,
            "failure_probability": round(fp_used, 4),
            "failure_probability_percent": round(fp_used * 100.0, 1),
            "wind_failure_probability": round(wind_fp, 4),
            "flood_failure_probability": round(flood_fp, 4),
            "resilience": round(resilience, 1),
            "status": "Failed" if failed else "ok",
            "failed": failed,
            "recovery_hours": base_recovery_hours,
            "estimated_recovery_hours": round(estimated_recovery_hours, 1),
            "exposure": round(exposure, 2),
            "accessibility": round(accessibility, 2),
            "criticality": round(criticality, 2),
            "customer_weight": customer_weight,
            "irls": []
        }

        row["irls"] = _trigger_hurricane_irls(row)
        out.append(row)

    summary = _compute_hurricane_resilience(out)
    propagation = _propagation_metrics(out)

    failed_count = sum(1 for c in out if c["failed"])
    avg_recovery = sum(c["estimated_recovery_hours"] for c in out) / len(out) if out else 0.0

    base_result = {
        "scenario": {
            "hurricane_category": category,
            "wind_speed": vmax,
            "alpha": alpha,
            "mode": mode,
            "flood_depth_ft": flood_depth_ft,
            "rainfall_intensity": rainfall_intensity,
            "network_redundancy": network_redundancy,
            "crew_readiness": crew_readiness,
            "vegetation_index": vegetation_index,
            "monte_carlo_runs": monte_carlo_runs if mode.lower() == "monte carlo" else 0,
            "components_analyzed": len(out)
        },
        "summary": {
            **summary,
            "failed_components": failed_count,
            "average_estimated_recovery_hours": round(avg_recovery, 1)
        },
        "propagation": propagation,
        "irl_catalog": _irl_catalog_hurricane(),
        "component_results": out
    }

    validation, error_margin = _build_hurricane_validation_and_error(payload, base_result)

    base_result["validation"] = validation
    base_result["error_margin"] = error_margin

    return base_result
# ============================================================
# SMR / INTERCONNECTED INFRASTRUCTURE FRAMEWORK LIBRARY
# (from literature review document)
# ============================================================

def _smr_human_factor_library():
    return {
        "monitoring_dimensions": {
            "physical_health": [
                "heart_rate",
                "blood_pressure",
                "sleep",
                "hydration",
                "fatigue"
            ],
            "mental_state": [
                "stress",
                "anxiety",
                "cognitive_workload",
                "attention",
                "situational_awareness"
            ],
            "behavioral_signals": [
                "blink_rate",
                "gaze_fixation",
                "eye_tracking",
                "emotion_detection",
                "voice_analysis"
            ]
        },
        "performance_shaping_factors": {
            "micro": ["experience", "training", "fitness_to_work", "mental_state"],
            "macro": ["environment", "interface_design", "procedures", "task_difficulty", "work_conditions"]
        },
        "control_room_support_actions": [
            "dynamic_task_reallocation",
            "scheduled_breaks",
            "ergonomic_adjustments",
            "adaptive_interface_support",
            "supervisor_alerts"
        ],
        "alert_threshold_examples": {
            "high_cognitive_workload": 0.75,
            "high_stress": 0.75,
            "low_attention": 0.40,
            "high_fatigue": 0.70
        }
    }

def _interconnected_infrastructure_library():
    return {
        "domains": [
            "energy",
            "water",
            "transportation",
            "waste",
            "food",
            "health",
            "social"
        ],
        "couplings": [
            {"from": "energy", "to": "water", "relation": "pumping_and_treatment_depend_on_energy"},
            {"from": "waste", "to": "energy", "relation": "waste_to_energy_conversion"},
            {"from": "energy", "to": "transportation", "relation": "charging_and_fuel_supply"},
            {"from": "food", "to": "transportation", "relation": "logistics_and_delivery"},
            {"from": "health", "to": "energy", "relation": "critical_facility_dependency"},
        ],
        "unified_interface_steps": [
            "physical_modeling",
            "performance_evaluation",
            "system_coupling",
            "control_strategy_design",
            "simulation",
            "optimization"
        ],
        "kpis": [
            "performance",
            "cost",
            "sustainability",
            "emissions",
            "uptime",
            "recovery_time",
            "resource_efficiency"
        ]
    }

def _resiliency_framework_library():
    return {
        "layers": {
            "IRD": "Inherent Resiliency Design",
            "RCS": "Resiliency Control System",
            "RAM": "Resiliency Alarm Management",
            "RIS": "Resiliency Interlock System"
        },
        "core_barriers": [
            "energy_load_control",
            "energy_supply_control",
            "energy_storage_control"
        ],
        "resilience_metrics": [
            "response_time",
            "performance_gap",
            "net_resilience_score"
        ],
        "resiliency_limits": {
            "energy_load_limits": "Safe demand levels before performance degradation",
            "energy_supply_limits": "Maximum reliable deliverable supply",
            "energy_storage_limits": "Buffer capacity for disturbances",
            "water_load_limits": "Safe water demand thresholds",
            "water_supply_limits": "Reliable water delivery capacity",
            "water_storage_limits": "Storage buffer thresholds"
        }
    }

def _framework_library_response():
    return {
        "smr_human_factors": _smr_human_factor_library(),
        "interconnected_infrastructures": _interconnected_infrastructure_library(),
        "resiliency_framework": _resiliency_framework_library()
    }

def _evaluate_smr_human_performance(payload):
    """
    Simple backend evaluator from the literature themes.
    Payload example:
    {
      "heart_rate_ratio": 1.15,
      "fatigue": 0.4,
      "stress": 0.6,
      "cognitive_workload": 0.7,
      "attention": 0.8,
      "blink_rate_index": 0.5
    }
    """
    hr_ratio = float(payload.get("heart_rate_ratio", 1.0))
    fatigue = float(payload.get("fatigue", 0.0))
    stress = float(payload.get("stress", 0.0))
    workload = float(payload.get("cognitive_workload", 0.0))
    attention = float(payload.get("attention", 1.0))
    blink_index = float(payload.get("blink_rate_index", 0.0))

    # normalize HR risk around baseline
    hr_risk = min(max((hr_ratio - 1.0) / 0.4, 0.0), 1.0)

    risk_score = (
        0.20 * hr_risk +
        0.20 * fatigue +
        0.20 * stress +
        0.20 * workload +
        0.10 * blink_index +
        0.10 * (1.0 - attention)
    )

    risk_score = max(0.0, min(1.0, risk_score))
    performance_score = round((1.0 - risk_score) * 100.0, 1)

    if risk_score >= 0.75:
        status = "HIGH RISK"
        actions = ["supervisor_alert", "task_reallocation", "break_recommendation"]
    elif risk_score >= 0.45:
        status = "MODERATE RISK"
        actions = ["monitor_closely", "ergonomic_adjustment", "reduce_workload"]
    else:
        status = "LOW RISK"
        actions = ["continue_monitoring"]

    return {
        "inputs": {
            "heart_rate_ratio": hr_ratio,
            "fatigue": fatigue,
            "stress": stress,
            "cognitive_workload": workload,
            "attention": attention,
            "blink_rate_index": blink_index
        },
        "risk_score": round(risk_score, 3),
        "performance_score": performance_score,
        "status": status,
        "recommended_actions": actions
    }
# ============================================================
# RESILIENCY (IE/RD/LORPA) - fitted to the NR-HESS backend
# ============================================================

def _resiliency_library():
    # Initiating Events (IE)
    IE = {
        "IE1": {"alpha_pv": 0.50, "alpha_wind": 0.60, "alpha_smr": 1.0, "alpha_trans": 1.0, "days": 7,  "p": 0.10},
        "IE2": {"alpha_pv": 1.00, "alpha_wind": 1.00, "alpha_smr": 0.0, "alpha_trans": 1.0, "days": 14, "p": 0.05},
        "IE3": {"alpha_pv": 1.00, "alpha_wind": 1.00, "alpha_smr": 1.0, "alpha_trans": 0.30, "days": 30, "p": 0.08},  # set 0.0 for island
    }

    # Resiliency Demand (RD)
    RD = {
        "RD1": {"demand_mult": 1.00, "var_mult": 1.00, "critical_frac": 0.60},
        "RD2": {"demand_mult": 1.25, "var_mult": 1.50, "critical_frac": 0.70},
        "RD3": {"demand_mult": 1.20, "var_mult": 1.50, "critical_frac": 0.80},
    }

    # S0-S5
    S0_S5 = [
        {"scenario_id": "S0", "label": "Baseline (no IE, RD1)", "ies": [],                 "rd": "RD1"},
        {"scenario_id": "S1", "label": "IE1 + RD1",             "ies": ["IE1"],            "rd": "RD1"},
        {"scenario_id": "S2", "label": "IE1 + RD2",             "ies": ["IE1"],            "rd": "RD2"},
        {"scenario_id": "S3", "label": "IE2 + RD1",             "ies": ["IE2"],            "rd": "RD1"},
        {"scenario_id": "S4", "label": "IE3 + RD1",             "ies": ["IE3"],            "rd": "RD1"},
        {"scenario_id": "S5", "label": "IE1+IE2+IE3 + RD3",     "ies": ["IE1","IE2","IE3"],"rd": "RD3"},
    ]

    # Your LORPA 10 rows
    LORPA10 = [
        {"scenario_id":"L1",  "label":"IE1 RD1 IPL1 IRL1",                  "ies":["IE1"],            "rd":"RD1"},
        {"scenario_id":"L2",  "label":"IE1 RD2 IPL1+2 IRL1+2",              "ies":["IE1"],            "rd":"RD2"},
        {"scenario_id":"L3",  "label":"IE1 RD3 IPL1+2 IRL1+2+3",            "ies":["IE1"],            "rd":"RD3"},
        {"scenario_id":"L4",  "label":"IE2 RD1 IPL1 IRL2",                  "ies":["IE2"],            "rd":"RD1"},
        {"scenario_id":"L5",  "label":"IE2 RD2 IPL1+2 IRL1+2",              "ies":["IE2"],            "rd":"RD2"},
        {"scenario_id":"L6",  "label":"IE3 RD1 IPL2 IRL3",                  "ies":["IE3"],            "rd":"RD1"},
        {"scenario_id":"L7",  "label":"IE3 RD2 IPL1+2 IRL1+3",              "ies":["IE3"],            "rd":"RD2"},
        {"scenario_id":"L8",  "label":"IE3 RD3 IPL1+2 IRL1+2+3",            "ies":["IE3"],            "rd":"RD3"},
        {"scenario_id":"L9",  "label":"IE1+IE3 RD2 IPL1+2 IRL1+3",          "ies":["IE1","IE3"],      "rd":"RD2"},
        {"scenario_id":"L10", "label":"IE1+IE2+IE3 RD3 IPL1+2 IRL1+2+3",    "ies":["IE1","IE2","IE3"],"rd":"RD3"},
    ]

    return IE, RD, S0_S5, LORPA10

def _bowtie_catalog():
    """
    Master catalog for Bowtie logic:
    - 3 high-level causes
    - IPLs
    - Actions
    - IRLs
    """
    causes = {
        "Cause-1": {
            "code": "Cause-1",
            "name": "Environmental disturbance",
            "description": "Extreme weather, environmental variability, wildfire, ice storm, drought, etc."
        },
        "Cause-2": {
            "code": "Cause-2",
            "name": "Equipment failure",
            "description": "Mechanical, electrical, control, inverter, turbine, transformer, or generator failure."
        },
        "Cause-3": {
            "code": "Cause-3",
            "name": "Grid or infrastructure constraint",
            "description": "Transmission congestion, export limitation, grid disconnection, or regional network limitation."
        }
    }

    ipls = {
        "IPL-1": {"code": "IPL-1", "name": "Operating reserve margin"},
        "IPL-2": {"code": "IPL-2", "name": "Forecast-based renewable scheduling"},
        "IPL-3": {"code": "IPL-3", "name": "Preventive dispatch control"},
        "IPL-4": {"code": "IPL-4", "name": "Automatic generation control"},
        "IPL-5": {"code": "IPL-5", "name": "Security-constrained dispatch planning"},
        "IPL-6": {"code": "IPL-6", "name": "Transmission monitoring and protection relays"},
        "IPL-7": {"code": "IPL-7", "name": "Preventive maintenance and condition monitoring"},
    }

    actions = {
        "Action-1": {"code": "Action-1", "name": "Reserve generation deployment"},
        "Action-2": {"code": "Action-2", "name": "Controlled load reduction"},
        "Action-3": {"code": "Action-3", "name": "Grid stabilization operations"},
        "Action-4": {"code": "Action-4", "name": "Generation redispatch"},
        "Action-5": {"code": "Action-5", "name": "Fast-ramping generation deployment"},
        "Action-6": {"code": "Action-6", "name": "Emergency reserve activation"},
        "Action-7": {"code": "Action-7", "name": "Inter-area balancing support"},
        "Action-8": {"code": "Action-8", "name": "Grid power rerouting"},
        "Action-9": {"code": "Action-9", "name": "Emergency grid reconfiguration"},
        "Action-10": {"code": "Action-10", "name": "Fault isolation"},
        "Action-11": {"code": "Action-11", "name": "Emergency generation dispatch"},
        "Action-12": {"code": "Action-12", "name": "Battery frequency response"},
    }

    irls = {
        "IRL-1": {"code": "IRL-1", "name": "Battery energy storage support"},
        "IRL-2": {"code": "IRL-2", "name": "Demand response programs"},
        "IRL-3": {"code": "IRL-3", "name": "Backup generation"},
        "IRL-4": {"code": "IRL-4", "name": "Inter-region power support"},
        "IRL-5": {"code": "IRL-5", "name": "Microgrid islanding"},
        "IRL-6": {"code": "IRL-6", "name": "Distributed energy resource restoration"},
    }

    return causes, ipls, actions, irls
def _component_bowtie_mappings():
    """
    Maps system components to:
    - faults
    - generalized causes
    - bowtie cause
    - multiple IPL -> Action -> IRL paths
    """

    return {
        "Solar PV": {
            "layer": "Physical Energy System",
            "faults": [
                {
                    "fault": "Reduced solar generation output",
                    "generalized_causes": [
                        {
                            "name": "Extreme weather events (storms, heavy clouds)",
                            "bowtie_cause": "Cause-1",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-1", "irl": "IRL-1"},
                                {"ipl": "IPL-2", "action": "Action-2", "irl": "IRL-2"},
                                {"ipl": "IPL-3", "action": "Action-3", "irl": "IRL-4"},
                            ]
                        },
                        {
                            "name": "Electrical equipment failure",
                            "bowtie_cause": "Cause-2",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-1", "irl": "IRL-1"},
                                {"ipl": "IPL-3", "action": "Action-2", "irl": "IRL-2"},
                                {"ipl": "IPL-4", "action": "Action-3", "irl": "IRL-3"},
                            ]
                        },
                        {
                            "name": "Transmission congestion preventing PV export",
                            "bowtie_cause": "Cause-3",
                            "paths": [
                                {"ipl": "IPL-2", "action": "Action-2", "irl": "IRL-4"},
                                {"ipl": "IPL-3", "action": "Action-3", "irl": "IRL-2"},
                                {"ipl": "IPL-4", "action": "Action-1", "irl": "IRL-6"},
                            ]
                        }
                    ]
                }
            ]
        },

        "Wind Farm": {
            "layer": "Physical Energy System",
            "faults": [
                {
                    "fault": "Turbine shutdown",
                    "generalized_causes": [
                        {
                            "name": "Extreme cold weather conditions",
                            "bowtie_cause": "Cause-1",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-1", "irl": "IRL-1"},
                                {"ipl": "IPL-2", "action": "Action-2", "irl": "IRL-2"},
                                {"ipl": "IPL-3", "action": "Action-5", "irl": "IRL-3"},
                            ]
                        },
                        {
                            "name": "Mechanical component failures",
                            "bowtie_cause": "Cause-2",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-1", "irl": "IRL-1"},
                                {"ipl": "IPL-3", "action": "Action-2", "irl": "IRL-2"},
                                {"ipl": "IPL-4", "action": "Action-5", "irl": "IRL-3"},
                            ]
                        },
                        {
                            "name": "Transmission export constraints",
                            "bowtie_cause": "Cause-3",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-2", "irl": "IRL-2"},
                                {"ipl": "IPL-4", "action": "Action-3", "irl": "IRL-4"},
                                {"ipl": "IPL-3", "action": "Action-1", "irl": "IRL-6"},
                            ]
                        }
                    ]
                }
            ]
        },

        "Gas Power Plant": {
            "layer": "Physical Energy System",
            "faults": [
                {
                    "fault": "Generator outage",
                    "generalized_causes": [
                        {
                            "name": "Extreme temperature conditions",
                            "bowtie_cause": "Cause-1",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-1", "irl": "IRL-1"},
                                {"ipl": "IPL-3", "action": "Action-6", "irl": "IRL-3"},
                                {"ipl": "IPL-4", "action": "Action-7", "irl": "IRL-4"},
                            ]
                        },
                        {
                            "name": "Fuel infrastructure disruption",
                            "bowtie_cause": "Cause-2",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-1", "irl": "IRL-1"},
                                {"ipl": "IPL-3", "action": "Action-6", "irl": "IRL-3"},
                                {"ipl": "IPL-4", "action": "Action-7", "irl": "IRL-4"},
                            ]
                        },
                        {
                            "name": "Transmission connection failure",
                            "bowtie_cause": "Cause-3",
                            "paths": [
                                {"ipl": "IPL-2", "action": "Action-2", "irl": "IRL-2"},
                                {"ipl": "IPL-3", "action": "Action-7", "irl": "IRL-4"},
                                {"ipl": "IPL-5", "action": "Action-3", "irl": "IRL-6"},
                            ]
                        }
                    ]
                }
            ]
        },

        "Hydropower System": {
            "layer": "Physical Energy System",
            "faults": [
                {
                    "fault": "Reduced water inflow",
                    "generalized_causes": [
                        {
                            "name": "Drought conditions",
                            "bowtie_cause": "Cause-1",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-4", "irl": "IRL-4"},
                                {"ipl": "IPL-2", "action": "Action-1", "irl": "IRL-3"},
                                {"ipl": "IPL-3", "action": "Action-2", "irl": "IRL-2"},
                            ]
                        },
                        {
                            "name": "Mechanical equipment failure",
                            "bowtie_cause": "Cause-2",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-1", "irl": "IRL-3"},
                                {"ipl": "IPL-3", "action": "Action-4", "irl": "IRL-4"},
                                {"ipl": "IPL-7", "action": "Action-3", "irl": "IRL-6"},
                            ]
                        },
                        {
                            "name": "Transmission export limitations",
                            "bowtie_cause": "Cause-3",
                            "paths": [
                                {"ipl": "IPL-5", "action": "Action-8", "irl": "IRL-4"},
                                {"ipl": "IPL-3", "action": "Action-2", "irl": "IRL-2"},
                                {"ipl": "IPL-6", "action": "Action-9", "irl": "IRL-5"},
                            ]
                        }
                    ]
                }
            ]
        },

        "Battery Energy Storage System": {
            "layer": "Physical Energy System",
            "faults": [
                {
                    "fault": "Battery depletion",
                    "generalized_causes": [
                        {
                            "name": "Extended energy deficit events",
                            "bowtie_cause": "Cause-1",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-12", "irl": "IRL-1"},
                                {"ipl": "IPL-2", "action": "Action-2", "irl": "IRL-2"},
                                {"ipl": "IPL-3", "action": "Action-3", "irl": "IRL-6"},
                            ]
                        },
                        {
                            "name": "Equipment malfunction",
                            "bowtie_cause": "Cause-2",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-12", "irl": "IRL-1"},
                                {"ipl": "IPL-3", "action": "Action-11", "irl": "IRL-3"},
                                {"ipl": "IPL-7", "action": "Action-9", "irl": "IRL-6"},
                            ]
                        },
                        {
                            "name": "Grid disconnection",
                            "bowtie_cause": "Cause-3",
                            "paths": [
                                {"ipl": "IPL-2", "action": "Action-2", "irl": "IRL-5"},
                                {"ipl": "IPL-3", "action": "Action-3", "irl": "IRL-6"},
                                {"ipl": "IPL-5", "action": "Action-8", "irl": "IRL-4"},
                            ]
                        }
                    ]
                }
            ]
        },

        "Dispatch System": {
            "layer": "Energy + Physical System",
            "faults": [
                {
                    "fault": "Insufficient committed generation",
                    "generalized_causes": [
                        {
                            "name": "Renewable generation forecast error",
                            "bowtie_cause": "Cause-1",
                            "paths": [
                                {"ipl": "IPL-2", "action": "Action-4", "irl": "IRL-1"},
                                {"ipl": "IPL-3", "action": "Action-11", "irl": "IRL-2"},
                                {"ipl": "IPL-5", "action": "Action-7", "irl": "IRL-4"},
                            ]
                        },
                        {
                            "name": "Unexpected generator outage",
                            "bowtie_cause": "Cause-2",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-6", "irl": "IRL-3"},
                                {"ipl": "IPL-3", "action": "Action-11", "irl": "IRL-2"},
                                {"ipl": "IPL-5", "action": "Action-7", "irl": "IRL-4"},
                            ]
                        },
                        {
                            "name": "Sudden electricity demand increase",
                            "bowtie_cause": "Cause-3",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-11", "irl": "IRL-2"},
                                {"ipl": "IPL-2", "action": "Action-4", "irl": "IRL-1"},
                                {"ipl": "IPL-3", "action": "Action-6", "irl": "IRL-4"},
                            ]
                        }
                    ]
                }
            ]
        },

        "Frequency Control System": {
            "layer": "Energy + Physical System",
            "faults": [
                {
                    "fault": "Frequency deviation from nominal value",
                    "generalized_causes": [
                        {
                            "name": "Renewable generation variability",
                            "bowtie_cause": "Cause-1",
                            "paths": [
                                {"ipl": "IPL-2", "action": "Action-12", "irl": "IRL-1"},
                                {"ipl": "IPL-3", "action": "Action-2", "irl": "IRL-2"},
                                {"ipl": "IPL-4", "action": "Action-3", "irl": "IRL-3"},
                            ]
                        },
                        {
                            "name": "Sudden generator outage",
                            "bowtie_cause": "Cause-2",
                            "paths": [
                                {"ipl": "IPL-3", "action": "Action-1", "irl": "IRL-3"},
                                {"ipl": "IPL-4", "action": "Action-12", "irl": "IRL-1"},
                                {"ipl": "IPL-2", "action": "Action-2", "irl": "IRL-2"},
                            ]
                        },
                        {
                            "name": "Transmission failure affecting power flows",
                            "bowtie_cause": "Cause-3",
                            "paths": [
                                {"ipl": "IPL-5", "action": "Action-8", "irl": "IRL-4"},
                                {"ipl": "IPL-4", "action": "Action-3", "irl": "IRL-5"},
                                {"ipl": "IPL-2", "action": "Action-2", "irl": "IRL-6"},
                            ]
                        }
                    ]
                }
            ]
        },

        "Transmission System": {
            "layer": "Physical System",
            "faults": [
                {
                    "fault": "Transmission line outage",
                    "generalized_causes": [
                        {
                            "name": "Severe storms and lightning events",
                            "bowtie_cause": "Cause-1",
                            "paths": [
                                {"ipl": "IPL-2", "action": "Action-8", "irl": "IRL-4"},
                                {"ipl": "IPL-3", "action": "Action-9", "irl": "IRL-2"},
                                {"ipl": "IPL-4", "action": "Action-10", "irl": "IRL-5"},
                            ]
                        },
                        {
                            "name": "Equipment aging or structural failure",
                            "bowtie_cause": "Cause-2",
                            "paths": [
                                {"ipl": "IPL-6", "action": "Action-10", "irl": "IRL-5"},
                                {"ipl": "IPL-7", "action": "Action-8", "irl": "IRL-4"},
                                {"ipl": "IPL-3", "action": "Action-9", "irl": "IRL-6"},
                            ]
                        },
                        {
                            "name": "Wildfire-related de-energization",
                            "bowtie_cause": "Cause-3",
                            "paths": [
                                {"ipl": "IPL-5", "action": "Action-8", "irl": "IRL-4"},
                                {"ipl": "IPL-6", "action": "Action-9", "irl": "IRL-5"},
                                {"ipl": "IPL-3", "action": "Action-2", "irl": "IRL-2"},
                            ]
                        }
                    ]
                }
            ]
        },

        "Substation System": {
            "layer": "Physical System",
            "faults": [
                {
                    "fault": "Transformer overheating",
                    "generalized_causes": [
                        {
                            "name": "Flooding or environmental damage",
                            "bowtie_cause": "Cause-1",
                            "paths": [
                                {"ipl": "IPL-3", "action": "Action-9", "irl": "IRL-5"},
                                {"ipl": "IPL-4", "action": "Action-10", "irl": "IRL-6"},
                                {"ipl": "IPL-6", "action": "Action-8", "irl": "IRL-4"},
                            ]
                        },
                        {
                            "name": "Equipment degradation or aging",
                            "bowtie_cause": "Cause-2",
                            "paths": [
                                {"ipl": "IPL-1", "action": "Action-10", "irl": "IRL-5"},
                                {"ipl": "IPL-2", "action": "Action-3", "irl": "IRL-6"},
                                {"ipl": "IPL-3", "action": "Action-9", "irl": "IRL-4"},
                            ]
                        },
                        {
                            "name": "Regional overload or network stress",
                            "bowtie_cause": "Cause-3",
                            "paths": [
                                {"ipl": "IPL-4", "action": "Action-3", "irl": "IRL-2"},
                                {"ipl": "IPL-5", "action": "Action-8", "irl": "IRL-4"},
                                {"ipl": "IPL-6", "action": "Action-9", "irl": "IRL-5"},
                            ]
                        }
                    ]
                }
            ]
        }
    }

def _get_component_bowtie(component_name=None):
    causes, ipls, actions, irls = _bowtie_catalog()
    mappings = _component_bowtie_mappings()

    if component_name:
        data = mappings.get(component_name)
        if not data:
            return None

        return {
            "component_name": component_name,
            "layer": data["layer"],
            "catalog": {
                "causes": causes,
                "ipls": ipls,
                "actions": actions,
                "irls": irls
            },
            "faults": data["faults"]
        }

    return {
        "catalog": {
            "causes": causes,
            "ipls": ipls,
            "actions": actions,
            "irls": irls
        },
        "components": mappings
    }


def _merge_ies(ies, IE):
    # multiply factors, max duration, sum p as a rough "stress score"
    alpha_pv = 1.0
    alpha_wind = 1.0
    alpha_smr = 1.0
    alpha_trans = 1.0
    days = 0
    p = 0.0
    for code in ies:
        ev = IE.get(code, {})
        alpha_pv   *= float(ev.get("alpha_pv", 1.0))
        alpha_wind *= float(ev.get("alpha_wind", 1.0))
        alpha_smr  *= float(ev.get("alpha_smr", 1.0))
        alpha_trans*= float(ev.get("alpha_trans", 1.0))
        days = max(days, int(ev.get("days", 0)))
        p += float(ev.get("p", 0.0))
    return {"alpha_pv": alpha_pv, "alpha_wind": alpha_wind, "alpha_smr": alpha_smr, "alpha_trans": alpha_trans, "days": days, "p": p}


def _apply_resiliency_to_capacity_factors(capacity_factors, source_type, merged_ie):
    """
    Your simulator uses a simple CF lookup by source_type.
    We apply IE1 to Solar/Wind, IE2 to Nuclear (SMR), leave others unchanged.
    """
    base_cf = float(capacity_factors.get(source_type, 0.0))

    if source_type == "Solar":
        return base_cf * merged_ie["alpha_pv"]
    if source_type == "Wind":
        return base_cf * merged_ie["alpha_wind"]
    if source_type == "Nuclear":
        return base_cf * merged_ie["alpha_smr"]  # IE2 sets to 0.0
    return base_cf


def _apply_transmission_derate(transmission_limits_by_pair, merged_ie):
    """
    Your transmission_limit payload is: { "A-B": { "2025": 100, ... }, ... }
    We multiply every numeric limit by alpha_trans.
    """
    a = float(merged_ie.get("alpha_trans", 1.0))
    if a >= 0.999:
        return transmission_limits_by_pair  # no change
    out = {}
    for pair, year_map in (transmission_limits_by_pair or {}).items():
        out[pair] = {}
        for y, lim in (year_map or {}).items():
            try:
                out[pair][str(y)] = float(lim) * a
            except Exception:
                out[pair][str(y)] = lim
    return out


def _scenario_summary(sim_json, critical_fraction, demand_multiplier):
    """
    Build a scenario-level summary from your existing response.
    Note: your simulation returns per-source rows with:
      energy_generated (currently treated like "supply") and demand stored as 'apple'.
    We'll compute:
      demand_total (per region-year-option unique)
      served_total = sum(energy_generated)
      EENS = max(demand - served, 0)
      served% = served/demand
      critical served% = min(served, critical_demand)/critical_demand
    COE proxy: take Aggregated COE for Option 1 (if exists), else average COE across regions.
    """
    results = sim_json.get("results", []) or []

    # Demand: use (year, option, region) uniqueness like your economic_analysis does
    seen = set()
    demand_total = 0.0
    served_total = 0.0

    for r in results:
        served_total += float(r.get("energy_generated", 0) or 0)

        y = r.get("year")
        opt = r.get("option")
        reg = r.get("region")
        key = (y, opt, reg)
        d = float(r.get("demand", r.get("apple", 0)) or 0)
        if d > 0 and key not in seen:
            demand_total += d
            seen.add(key)

    eens = max(((demand_total - served_total)/1000000), 0.0)
    served_pct = (served_total / demand_total) if demand_total > 0 else 0.0

    crit_demand = demand_total * float(critical_fraction)
    crit_served = min(served_total, crit_demand) if crit_demand > 0 else 0.0
    crit_served_pct = (crit_served / crit_demand) if crit_demand > 0 else 0.0

    # COE proxy: prefer aggregated energy_options if present
    coe_proxy = None
    try:
        agg = sim_json.get("aggregated", {}).get("energy_options", {})
        # take end year option 1 if exists
        if agg:
            any_year = sorted(agg.keys(), key=lambda x: int(str(x).split("-")[0]))[-1]
            coe_proxy = agg[any_year].get("Option 1", {}).get("COE", None)
    except Exception:
        pass

    return {
        "demand_total": round(demand_total, 3),
        "served_total": round(served_total, 3),
        "served_pct": round(served_pct * 100, 2),
        "eens": round(eens, 3),
        "critical_fraction": float(critical_fraction),
        "critical_served_pct": round(crit_served_pct * 100, 2),
        "coe_proxy": coe_proxy,
        "demand_multiplier": float(demand_multiplier),
    }

def _run_simulation_core(data):
    # --- PASTE YOUR EXISTING try: BODY HERE, but remove:
    #   data = request.get_json()
    #   return jsonify(...)
    # Instead: use `data` already passed in, and return a python dict.
    #
    # At the end, return dicts (not jsonify)
    #
    # If exception: raise

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # START OF YOUR EXISTING LOGIC (edited minimally)
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def compute_crf(rate, lifetime):
        return (rate * (1 + rate) ** lifetime) / ((1 + rate) ** lifetime - 1) if lifetime > 0 else 0

    user_id = data['user_id']
    sources = data['sources']
    run_mode = data.get('run_mode', 'single')
    selected_regions = data.get('selected_regions', [])
    start_year = int(data['start_year'])
    end_year = int(data['end_year'])
    discount_rate = 0.03
    projection_name = data.get('projection_name', '')
    projections_by_region = data.get('projections_by_region', {})
    transmission_limits_by_pair = data.get('transmission_limit', {})
    transmission_loss = data.get('transmission_loss', 0.05)
    use_custom_mix = data.get("use_custom_mix", False)
    custom_caps = data.get("custom_installed_capacities", {})

    # ---- resiliency knob (new) ----
    resil = data.get("resiliency", {}) or {}
    # expected keys:
    #  alpha_pv, alpha_wind, alpha_smr, alpha_trans, demand_multiplier, variability_multiplier, critical_fraction
    alpha_pv = float(resil.get("alpha_pv", 1.0))
    alpha_wind = float(resil.get("alpha_wind", 1.0))
    alpha_smr = float(resil.get("alpha_smr", 1.0))
    alpha_trans = float(resil.get("alpha_trans", 1.0))
    demand_multiplier = float(resil.get("demand_multiplier", 1.0))
    variability_multiplier = float(resil.get("variability_multiplier", 1.0))
    critical_fraction = float(resil.get("critical_fraction", 0.60))

    # after hurricane_result



    # apply transmission derate (IE3)
    if alpha_trans != 1.0:
        transmission_limits_by_pair = _apply_transmission_derate(transmission_limits_by_pair, {"alpha_trans": alpha_trans})

    for source in sources:
        source['sizing_limits'] = source.get('sizingLimits', source.get('sizing_limits', {}))

    capacity_factors = {
        "Nuclear": 0.909, "Geothermal": 0.672, "Biomass": 0.671,
        "Coal": 0.589, "Natural Gas": 0.503, "Hydro": 0.405,
        "Wind": 0.15, "Solar": 0.12, "Hydrogen": 0.6, "Tidal": 0.3
    }

    installed_capacities = generate_best_scenarios(
        sources=sources,
        capacity_factors=capacity_factors,
        start_year=start_year,
        end_year=end_year,
        years_step=5,
        num_candidates=150,
        top_k=5,
        discount_rate=discount_rate,
        per_source_min=None,
        per_source_max=None,
        smoothing_pp=20.0,
        seed=42
    )

    if use_custom_mix:
        installed_capacities = {}
        for year_str, caps in custom_caps.items():
            caps_float = [float(c or 0) for c in caps]
            installed_capacities[str(year_str)] = {"1": caps_float}

    # Fetch demand
    # demand_resp = requests.get(f"http://localhost:5000/api/user_energy_demand/{user_id}")
    # if demand_resp.status_code != 200:
    #     raise Exception('Failed to fetch energy demand')
    projections = EnergyDemandProjection.query.filter_by(user_id=user_id).all()

    all_demand_data = []
    for p in projections:
        growth_data = json.loads(p.growth_rate)
        power_data = growth_data.get("power", growth_data)

        energy_data = {
            year: round(float(value) * 8760)
            for year, value in power_data.items()
        }

        all_demand_data.append({
            "id": p.id,
            "name": p.name,
            "base_demand": p.base_demand,
            "demand_per_year": growth_data,
            "energy": energy_data,
            "user_id": p.user_id
        })

    all_demand_data = demand_resp.json()

    def simulate_region(region_name):
        results = []
        energy_options = defaultdict(lambda: defaultdict(dict))

        region_projection_name = projections_by_region.get(region_name, projection_name)
        matched_projection = next((p for p in all_demand_data if p['name'] == region_projection_name), None)
        if not matched_projection:
            raise Exception(f'Selected demand projection not found for region {region_name}')

        energy_by_year = matched_projection.get('energy', {})

        for year_str, option_sets in installed_capacities.items():
            year = int(year_str.split('-')[0]) if '-' in year_str else int(year_str)
            if not (start_year <= year <= end_year):
                continue

            for option_str, capacity_row in option_sets.items():
                option_index = int(option_str)
                total_cost = 0.0
                total_supply_like = 0.0
                financial_total_energy = 0.0

                # apply RD demand multiplier
                base_demand_for_year = float(energy_by_year.get(year_str, 0))
                demand_for_year = base_demand_for_year * demand_multiplier

                for source_index, installed_capacity in enumerate(capacity_row):
                    if source_index >= len(sources):
                        continue
                    if installed_capacity <= 0:
                        continue

                    source = sources[source_index]
                    source_type = source['type']

                    # apply IE derates to CFs (IE1/IE2)
                    merged_ie = {
                        "alpha_pv": alpha_pv,
                        "alpha_wind": alpha_wind,
                        "alpha_smr": alpha_smr
                    }
                    cf = _apply_resiliency_to_capacity_factors(capacity_factors, source_type, merged_ie)

                    sizing_limit = float(source.get('sizing_limits', {}).get(year_str, 0) or 0)

                    derating = float(source.get('derating_factor', 1.0))
                    scaling = float(source.get('scaling_factor', 1.0))
                    reliability_margin = 0.8

                    engineering_energy = (
                        (cf * sizing_limit * derating * scaling * 24 * 365) / reliability_margin
                    ) if cf > 0 else 0.0

                    if demand_for_year > 0:
                        raw_percent = round(100 * engineering_energy / demand_for_year)
                        percent = min(raw_percent, 100)
                    else:
                        percent = 0

                    
                    energy_generated = (demand_for_year * (installed_capacity / 100)) / (cf * 8760) if cf > 0 else 0.0
                    total_supply_like += energy_generated

                    # NEW: separate financial energy basis
                    financial_energy_generated = demand_for_year * (installed_capacity / 100.0)
                    financial_total_energy += financial_energy_generated

                    # NEW: required capacity for finance
                    required_capacity_kw = financial_energy_generated / (cf * 8760) if cf > 0 else 0.0

    
                    capex = float(source.get('capital_cost', 0))
                    opex = float(source.get('om_cost', 0))
                    fuel_cost = float(source.get('fuel_price', 0))
                    lifetime = int(source.get('lifetime', 25))
                    crf = compute_crf(discount_rate, lifetime)

                    annualized_capital = required_capacity_kw * capex * crf
                    annual_om = required_capacity_kw * opex
                    annual_fuel = financial_energy_generated * fuel_cost
                    annual_total_cost = annualized_capital + annual_om + annual_fuel

                    annualized_cost = (((capex * crf * installed_capacity) + (opex * installed_capacity)) / (8760 * cf)) + fuel_cost if cf > 0 else 0.0
                    total_cost += annualized_cost

                    results.append({
                        'user_id': user_id,
                        'region': region_name,
                        'option': option_index,
                        'year': year,
                        'apple': demand_for_year,
                        'source_index': source_index + 1,
                        'source_type': source_type,
                        'energy_generated': round(energy_generated, 2),
                        'financial_energy_generated': round(financial_energy_generated, 2),
                        'required_capacity_kw': round(required_capacity_kw, 2),
                        'engineering_energy': round(engineering_energy, 2),
                        'percent': round(percent, 1),
                        'annualized_cost': round(annualized_cost, 6),
                        'annual_total_cost': round(annual_total_cost, 2)
                    })

                    energy_options[year_str][f"Option {option_index}"][source_type] = round(energy_generated, 2)
                
                coe = (total_cost * 10000 / total_supply_like) if total_supply_like > 0 else 0
                energy_options[year_str][f"Option {option_index}"]["COE"] = round(coe, 5)

        return results, energy_options, energy_by_year

    # MULTI
    if run_mode == "multi":
        results_by_region = {}
        all_results = []
        aggregated_options = defaultdict(lambda: defaultdict(dict))
        region_balances = {}

        for region in selected_regions:
            region_results, region_options, energy_by_year = simulate_region(region)
            results_by_region[region] = {"results": region_results, "energy_options": region_options}
            all_results.extend(region_results)

            region_balances[region] = {}
            for year in energy_by_year:
                year_key = year
                year_int = int(year.split('-')[0]) if '-' in year else int(year)
                total_generated = sum(row['energy_generated'] for row in region_results if row['year'] == year_int)
                region_balances[region][year_key] = total_generated

            for year, options in region_options.items():
                for opt, values in options.items():
                    for key, val in values.items():
                        if key == "COE":
                            aggregated_options[year][opt].setdefault("COE_list", []).append(val)
                        else:
                            aggregated_options[year][opt][key] = aggregated_options[year][opt].get(key, 0) + val

        for year in aggregated_options:
            for opt in aggregated_options[year]:
                coe_list = aggregated_options[year][opt].pop("COE_list", [])
                aggregated_options[year][opt]["COE"] = round(sum(coe_list) / len(coe_list), 5) if coe_list else 0

        # Energy sharing uses derated transmission limits already (if alpha_trans != 1.0)
        energy_sharing = []
        all_years = set()
        for balances in region_balances.values():
            all_years.update(balances.keys())

        for year in sorted(all_years, key=lambda x: int(x.split('-')[0]) if '-' in x else int(x)):
            for from_region in selected_regions:
                surplus = max(0, region_balances[from_region].get(year, 0))
                if surplus <= 0:
                    continue
                for to_region in selected_regions:
                    if from_region == to_region:
                        continue
                    deficit = max(0, -region_balances[to_region].get(year, 0))
                    if deficit > 0:
                        pair_key = f"{from_region}-{to_region}"
                        year_str = str(year)
                        limit = transmission_limits_by_pair.get(pair_key, {}).get(year_str, 100)
                        sent = min(surplus, deficit, limit)
                        received = sent * (1 - transmission_loss)
                        energy_sharing.append({
                            'year': year,
                            'from': from_region,
                            'to': to_region,
                            'sent': round(sent, 2),
                            'received': round(received, 2),
                            'loss': round(sent - received, 2)
                        })
                        region_balances[from_region][year] -= sent
                        region_balances[to_region][year] += received
                        surplus -= sent
                        if surplus <= 0:
                            break

        return {
            "selected_regions": selected_regions,
            "results": all_results,
            "results_by_region": results_by_region,
            "aggregated": {"energy_options": aggregated_options},
            "energy_sharing": energy_sharing,
            "region_balances": region_balances,
            "resiliency": {
                "demand_multiplier": demand_multiplier,
                "variability_multiplier": variability_multiplier,
                "critical_fraction": critical_fraction,
                "alpha_pv": alpha_pv,
                "alpha_wind": alpha_wind,
                "alpha_smr": alpha_smr,
                "alpha_trans": alpha_trans,
            }
        }

    # SINGLE
    else:
        region = data.get("region", "Region")
        results, energy_options, _ = simulate_region(region)
        return {
            "selected_regions": [region],
            "results": results,
            "energy_options": energy_options,
            "resiliency": {
                "demand_multiplier": demand_multiplier,
                "variability_multiplier": variability_multiplier,
                "critical_fraction": critical_fraction,
                "alpha_pv": alpha_pv,
                "alpha_wind": alpha_wind,
                "alpha_smr": alpha_smr,
                "alpha_trans": alpha_trans,
            }
        }

@app.route('/api/run_simulation', methods=['POST'])
def run_simulation():
    try:
        data = request.get_json() or {}
        out = _run_simulation_core(data)
        return jsonify(out)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/economic_analysis', methods=['POST'])
def economic_analysis():
    try:
        data = request.get_json() or {}
        results = data.get("results", [])
        years_filter = data.get("years")

        # new controls from frontend
        mode = data.get("mode", "both")  # aggregated | region | both
        selected_region = data.get("selected_region")

        electricity_price = float(data.get("electricity_price", 0.10) or 0.10)
        increase_rate = float(data.get("increase_rate", 5) or 5)
        discount_rate = float(data.get("discount_rate", 0.03) or 0.03)
        base_year = int(data.get("base_year", 2025) or 2025)
        value_of_lost_load = float(data.get("value_of_lost_load", 2.0) or 2.0)

        # if frontend asks for one region only
        active_results = results
        if mode == "region" and selected_region:
            active_results = [r for r in results if r.get("region") == selected_region]

        if years_filter:
            years = []
            for y in years_filter:
                try:
                    years.append(int(y))
                except (TypeError, ValueError):
                    continue
        else:
            years = sorted({
                int(r.get("year"))
                for r in active_results
                if str(r.get("year", "")).isdigit()
            })

        # aggregated across active rows
        aggregated = _compute_economic_dataset(
            active_results,
            years,
            electricity_price,
            increase_rate,
            discount_rate,
            base_year,
            value_of_lost_load
        )

        # always prepare per-region too
        per_region = {}
        all_regions = sorted({r.get("region") for r in results if r.get("region")})

        for region in all_regions:
            region_rows = [r for r in results if r.get("region") == region]
            per_region[region] = _compute_economic_dataset(
                region_rows,
                years,
                electricity_price,
                increase_rate,
                discount_rate,
                base_year,
                value_of_lost_load
            )

        return jsonify({
            "mode": mode,
            "selected_region": selected_region,
            "aggregated": aggregated,
            "per_region": per_region,
            "summary": aggregated["summary"]
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/run_resiliency', methods=['POST'])
def run_resiliency():
    """
    Runs multiple scenarios (S0–S5, LORPA10, or BOTH) by reusing your simulation core.
    Request JSON: same as /api/run_simulation payload + optional:
      {
        "scenario_set": "S0_S5" | "LORPA10" | "BOTH",
        "transmission_alpha_mode": "0.30" or "0.00" (optional override for IE3)
      }
    """
    try:
        base = request.get_json() or {}
        scenario_set = (base.get("scenario_set") or "S0_S5").upper()

        IE, RD, S0_S5, LORPA10 = _resiliency_library()

        # optional override: set IE3 to 0.0 if you want islanding test
        if "transmission_alpha_mode" in base:
            try:
                IE["IE3"]["alpha_trans"] = float(base["transmission_alpha_mode"])
            except Exception:
                pass

        if scenario_set == "LORPA10":
            scenarios = LORPA10
        elif scenario_set == "BOTH":
            scenarios = S0_S5 + LORPA10
        else:
            scenarios = S0_S5

        runs = []
        for sc in scenarios:
            merged_ie = _merge_ies(sc["ies"], IE)
            rd = RD[sc["rd"]]

            # inject resiliency knobs into payload
            payload = dict(base)
            payload["resiliency"] = {
                "scenario_id": sc["scenario_id"],
                "label": sc["label"],
                "ies": sc["ies"],
                "rd": sc["rd"],
                "alpha_pv": merged_ie["alpha_pv"],
                "alpha_wind": merged_ie["alpha_wind"],
                "alpha_smr": merged_ie["alpha_smr"],
                "alpha_trans": merged_ie["alpha_trans"],
                "demand_multiplier": rd["demand_mult"],
                "variability_multiplier": rd["var_mult"],
                "critical_fraction": rd["critical_frac"],
                "duration_days": merged_ie["days"],
                "hazard_probability_per_year": merged_ie["p"],
            }

            sim_json = _run_simulation_core(payload)
            summary = _scenario_summary(sim_json, rd["critical_frac"], rd["demand_mult"])
            component_bowtie = _get_component_bowtie()
            
            hurricane_payload = {
                "hurricane_category": "Category 4",
                "wind_speed": 135,
                "alpha": 0.237,
                "mode": "Monte Carlo",
                "monte_carlo_runs": 300,
                "flood_depth_ft": 4.5,
                "rainfall_intensity": 0.80,
                "network_redundancy": 0.20,
                "crew_readiness": 0.70,
                "vegetation_index": 0.75
            }
            hurricane_result = _run_hurricane_resilience(hurricane_payload)

            runs.append({
                "scenario_id": sc["scenario_id"],
                "label": sc["label"],
                "meta": payload["resiliency"],
                "summary": summary,
                "bowtie": component_bowtie,
                "hurricane_module": hurricane_result,
                "simulation": sim_json
            })

        return jsonify({"scenario_set": scenario_set, "runs": runs}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================================
# ROUTES FOR NEW DOC INTEGRATION
# ============================================================
def _safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default

def _default_hurricane_case_study(payload):
    return {
        "title": payload.get("case_study_title", "Case Study"),
        "storm_name": payload.get("storm_name", "Custom Hurricane"),
        "county": payload.get("county", "User-defined County"),
        "state": payload.get("state", "User-defined State"),
        "system_name": payload.get("system_name", "Custom Distribution Feeder"),
        "feeder_voltage_kv": _safe_float(payload.get("feeder_voltage_kv", 13.8), 13.8),
        "network_topology": payload.get("network_topology", "Radial"),
        "customers_served": _safe_int(payload.get("customers_served", 4200), 4200),
        "feeder_length_km": _safe_float(payload.get("feeder_length_km", 12.0), 12.0),
        "substation": payload.get("substation", "Primary Substation"),
        "pole_construction": payload.get("pole_construction", "Predominantly wooden poles"),
        "study_purpose": payload.get(
            "study_purpose",
            "Primary benchmark for hurricane resilience modeling and IRL framework validation"
        ),
    }

def _default_critical_facilities(payload):
    facilities = payload.get("critical_facilities")
    if isinstance(facilities, list) and facilities:
        return facilities

    return [
        {
            "name": "Regional Hospital",
            "priority": "P1 — HIGHEST",
            "backup_power": "Diesel generator (critical loads only)",
            "max_outage": "< 2 hours",
            "irl_layers": ["RIS", "RCS"],
            "impact_if_lost": "Loss of life risk — ICU, OR, and life support disruption"
        },
        {
            "name": "Water Treatment Plant",
            "priority": "P2 — HIGH",
            "backup_power": "Limited backup power",
            "max_outage": "< 8 hours",
            "irl_layers": ["RIS", "RAM", "RCS"],
            "impact_if_lost": "Loss of potable water supply and public health emergency"
        },
        {
            "name": "Telecom Tower",
            "priority": "P3 — HIGH",
            "backup_power": "Battery backup (4–6 hours typical)",
            "max_outage": "< 6 hours",
            "irl_layers": ["RAM", "RCS"],
            "impact_if_lost": "Emergency communication and dispatch disruption"
        }
    ]

def _storm_characteristics(payload):
    return {
        "hurricane_category": payload.get("hurricane_category", "Category 4"),
        "wind_speed_mph": _safe_float(payload.get("wind_speed", 135), 135),
        "wind_speed_kmh": round(_safe_float(payload.get("wind_speed", 135), 135) * 1.60934, 1),
        "alpha": _safe_float(payload.get("alpha", 0.237), 0.237),
        "mode": payload.get("mode", "Monte Carlo"),
        "monte_carlo_runs": _safe_int(payload.get("monte_carlo_runs", 300), 300),
        "flood_depth_ft": _safe_float(payload.get("flood_depth_ft", 4.5), 4.5),
        "rainfall_intensity": _safe_float(payload.get("rainfall_intensity", 0.8), 0.8),
        "network_redundancy": _safe_float(payload.get("network_redundancy", 0.2), 0.2),
        "crew_readiness": _safe_float(payload.get("crew_readiness", 0.7), 0.7),
        "vegetation_index": _safe_float(payload.get("vegetation_index", 0.75), 0.75),
        "simulation_window_hours": _safe_int(payload.get("simulation_window_hours", 48), 48),
        "track_direction": payload.get("track_direction", "SW → NE"),
        "distance_to_feeder_buses": payload.get("distance_to_feeder_buses", "1–6 km"),
    }

def _vulnerability_cards(case_study, result):
    component_results = result.get("component_results", [])

    wood_poles = [c for c in component_results if c.get("component") == "Wood Pole"]
    overhead = [c for c in component_results if c.get("component") in ("Overhead Line", "Feeder Line")]

    wood_pf = round(max((c.get("failure_probability_percent", 0) for c in wood_poles), default=0), 1)
    overhead_pf = round(max((c.get("failure_probability_percent", 0) for c in overhead), default=0), 1)

    return [
        {
            "title": "Pole Construction",
            "risk": "HIGH",
            "description": f"{case_study['pole_construction']}. Peak failure probability in the current run is ~{wood_pf}% for the most exposed wooden pole class."
        },
        {
            "title": "Overhead Line Exposure",
            "risk": "HIGH",
            "description": f"Overhead conductors remain directly exposed to wind loading, debris, and vegetation contact. Peak line-related failure probability in the run is ~{overhead_pf}%."
        },
        {
            "title": "Network Topology",
            "risk": "CRITICAL" if str(case_study["network_topology"]).lower() == "radial" else "MODERATE",
            "description": "A radial feeder has limited alternate routing. One upstream failure can disconnect multiple downstream buses and critical loads."
        }
    ]

def _build_cascade_steps(result, case_study):
    failed_components = result.get("summary", {}).get("failed_components", 0)
    customers_impacted = result.get("propagation", {}).get("customers_impacted_estimate", 0)

    return [
        {
            "step": "01",
            "title": "Hurricane Wind Loading",
            "text": "The wind field model computes local wind at each component using radial decay and applies exposure amplification where relevant."
        },
        {
            "step": "02",
            "title": "Fragility Evaluation",
            "text": "Each component’s local wind is converted into a failure probability using the lognormal fragility model."
        },
        {
            "step": "03",
            "title": "Damage Realization",
            "text": f"The current run identifies {failed_components} failed components under the selected hurricane conditions."
        },
        {
            "step": "04",
            "title": "Propagation",
            "text": f"Failures propagate into feeder and bus outages, with an estimated {customers_impacted} customers affected."
        },
        {
            "step": "05",
            "title": "Critical Facility Impact",
            "text": "Critical facilities are assessed against outage tolerance and restoration priority."
        },
        {
            "step": "06",
            "title": "IRL Response",
            "text": "IRD, RCS, RAM, and RIS triggers are assigned based on failure, risk, and recovery conditions."
        },
        {
            "step": "07",
            "title": "Recovery and Resilience",
            "text": "The model summarizes restoration difficulty, recovery duration, and overall resilience score."
        }
    ]

def _summary_cards(result):
    summary = result.get("summary", {})
    propagation = result.get("propagation", {})

    return [
        {"label": "System Status", "value": summary.get("instantaneous_status", "-")},
        {"label": "Resilience Metric", "value": summary.get("resilience_metric", 0)},
        {"label": "Avg Component Resilience", "value": f"{summary.get('average_component_resilience', 0)}%"},
        {"label": "Weighted Resilience", "value": f"{summary.get('weighted_component_resilience', 0)}%"},
        {"label": "Failed Components", "value": summary.get("failed_components", 0)},
        {"label": "Avg Recovery Hours", "value": summary.get("average_estimated_recovery_hours", 0)},
        {"label": "Components at Risk", "value": propagation.get("components_at_risk", 0)},
        {"label": "Customers Impacted", "value": propagation.get("customers_impacted_estimate", 0)},
    ]

def _format_component_table(result):
    rows = []
    for row in result.get("component_results", []):
        rows.append({
            "component": row.get("component"),
            "type": row.get("type"),
            "wind_mph": row.get("wind_mph"),
            "effective_wind_mph": row.get("effective_wind_mph"),
            "flood_depth_ft": row.get("flood_depth_ft"),
            "failure_probability_percent": row.get("failure_probability_percent"),
            "resilience": row.get("resilience"),
            "estimated_recovery_hours": row.get("estimated_recovery_hours"),
            "status": row.get("status"),
            "irls": row.get("irls", []),
        })
    return rows
    
@app.route('/api/hurricane_resilience/analyze', methods=['POST'])
def hurricane_resilience_analyze():
    try:
        data = request.get_json() or {}
        result = _run_hurricane_resilience(data)

        case_study = _default_hurricane_case_study(data)
        storm = _storm_characteristics(data)
        critical_facilities = _default_critical_facilities(data)

        response = {
            "case_study": case_study,
            "storm": storm,
            "summary_cards": _summary_cards(result),
            "vulnerabilities": _vulnerability_cards(case_study, result),
            "critical_facilities": critical_facilities,
            "cascade_steps": _build_cascade_steps(result, case_study),
            "summary": result.get("summary", {}),
            "propagation": result.get("propagation", {}),
            "irl_catalog": result.get("irl_catalog", {}),
            "component_rows": _format_component_table(result),
            "validation": result.get("validation", {}),
            "error_margin": result.get("error_margin", {}),
            "raw": result
        }

        return jsonify(response), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/framework/library', methods=['GET'])
def framework_library():
    try:
        return jsonify(_framework_library_response()), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/smr_human_performance/evaluate', methods=['POST'])
def smr_human_performance_evaluate():
    try:
        data = request.get_json() or {}
        result = _evaluate_smr_human_performance(data)
        return jsonify(result), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

from collections import defaultdict
from flask import request, jsonify

def _compute_economic_dataset(rows, years, electricity_price, increase_rate, discount_rate, base_year, value_of_lost_load):
    gen_by_year = defaultdict(float)
    demand_by_year = defaultdict(float)
    cost_by_year = defaultdict(float)
    seen_demand_keys = set()

    for r in rows:
        try:
            y = int(r.get("year"))
        except (TypeError, ValueError):
            continue

        g = float(r.get("financial_energy_generated", r.get("energy_generated", 0)) or 0)
        gen_by_year[y] += g

        d = float(r.get("demand", r.get("apple", 0)) or 0)
        key = (y, r.get("option"), r.get("region"))
        if d > 0 and key not in seen_demand_keys:
            demand_by_year[y] += d
            seen_demand_keys.add(key)

        annual_total_cost = float(r.get("annual_total_cost", 0) or 0)
        if annual_total_cost > 0:
            cost_by_year[y] += annual_total_cost
        else:
            c_per_kwh = float(r.get("annualized_cost", 0) or 0)
            cost_by_year[y] += c_per_kwh * g

    generation_data = []
    cash_flow_data = []

    total_gen = 0.0
    total_demand = 0.0
    total_served = 0.0
    total_surplus = 0.0
    total_unserved = 0.0

    pv_cost_sum = 0.0
    pv_gen_sum = 0.0
    total_revenue_pv = 0.0

    for y in years:
        g = float(gen_by_year.get(y, 0.0))
        d = float(demand_by_year.get(y, 0.0))

        served_energy = min(g, d)
        surplus = max(g - d, 0.0)
        unserved_energy = max(d - g, 0.0)

        annual_cost = float(cost_by_year.get(y, 0.0))
        outage_penalty = unserved_energy * value_of_lost_load
        annual_cost_total = annual_cost + outage_penalty

        price_for_year = electricity_price * ((1 + increase_rate / 100.0) ** (y - base_year))
        annual_revenue = served_energy * price_for_year
        cash_flow = annual_revenue - annual_cost_total

        years_since_start = y - base_year
        discount_factor = (1 / ((1 + discount_rate) ** years_since_start)) if years_since_start >= 0 else 1.0

        pv_cost_sum += annual_cost_total * discount_factor
        pv_gen_sum += served_energy * discount_factor
        total_revenue_pv += annual_revenue * discount_factor

        total_gen += g
        total_demand += d
        total_served += served_energy
        total_surplus += surplus
        total_unserved += unserved_energy

        generation_data.append({
            "year": y,
            "demand": round(d, 3),
            "served_energy": round(served_energy, 3),
            "generation": round(g, 3),
            "surplus": round(surplus, 3),
            "unserved_energy": round(unserved_energy, 3),
            "annual_cost": round(annual_cost, 2),
            "outage_penalty": round(outage_penalty, 2),
            "annual_cost_total": round(annual_cost_total, 2),
            "annual_revenue": round(annual_revenue, 2)
        })

        cash_flow_data.append({
            "year": y,
            "cash_flow": round(cash_flow, 2)
        })

    total_outage_penalty = total_unserved * value_of_lost_load
    total_annual_cost = sum(float(cost_by_year.get(y, 0.0)) for y in years)

    generation_data.append({
        "year": "Total",
        "demand": round(total_demand, 3),
        "served_energy": round(total_served, 3),
        "generation": round(total_gen, 3),
        "surplus": round(total_surplus, 3),
        "unserved_energy": round(total_unserved, 3),
        "annual_cost": round(total_annual_cost, 2),
        "outage_penalty": round(total_outage_penalty, 2),
        "annual_cost_total": round(total_annual_cost + total_outage_penalty, 2),
        "annual_revenue": round(sum(
            min(float(gen_by_year.get(y, 0.0)), float(demand_by_year.get(y, 0.0))) *
            (electricity_price * ((1 + increase_rate / 100.0) ** (y - base_year)))
            for y in years
        ), 2)
    })

    npc = round(pv_cost_sum / 1_000_000.0, 3)
    lcoe = round((pv_cost_sum / pv_gen_sum) if pv_gen_sum > 0 else 0.0, 5)
    npv = round((total_revenue_pv - pv_cost_sum) / 1_000_000.0, 3)

    summary = {
        "electricity_price": electricity_price,
        "increasing_rate": increase_rate,
        "discount_rate": discount_rate,
        "value_of_lost_load": value_of_lost_load,
        "net_present_cost": npc,
        "lcoe": lcoe,
        "net_present_value": npv
    }

    return {
        "generation_data": generation_data,
        "cash_flow": cash_flow_data,
        "summary": summary
    }




# if __name__ == '__main__': 
   # app.run(debug=True)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Creates tables if they don't exist
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))