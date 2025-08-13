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


app = Flask(__name__)
bcrypt = Bcrypt(app)


username = "root"
password = "1234"
database = "Airplane_System"

app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{username}:{password}@localhost:3000/{database}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
CORS(app)

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

    
@app.route('/api/run_simulation', methods=['POST'])
def run_simulation():
    try:
        def compute_crf(rate, lifetime):
            return (rate * (1 + rate) ** lifetime) / ((1 + rate) ** lifetime - 1) if lifetime > 0 else 0

        data = request.get_json()
        user_id = data['user_id']
        sources = data['sources']
        run_mode = data.get('run_mode', 'single')
        selected_regions = data.get('selected_regions', [])
        start_year = int(data['start_year'])
        end_year = int(data['end_year'])
        discount_rate = 0.03
        projection_name = data.get('projection_name', '')
        projections_by_region = data.get('projections_by_region', {})
        transmission_limit_by_year = data.get('transmission_limit', {})
        transmission_loss = data.get('transmission_loss', 0.05)
        use_custom_mix = data.get("use_custom_mix", False)
        custom_caps = data.get("custom_installed_capacities", {})
        transmission_recipients = data.get('transmission_recipients', {})



        for source in sources:
            source['sizing_limits'] = source.get('sizingLimits', source.get('sizing_limits', {}))

        installed_capacities = {
            "2025": {"1": [0, 0, 0, 70, 30], "2": [4, 16, 80, 0, 0], "3": [2, 8, 90, 0, 0], "4": [6, 14, 80, 0, 0], "5": [4, 6, 90, 0, 0]},
            "2030": {"1": [0, 0, 0, 70, 30], "2": [4, 16, 80, 0, 0], "3": [2, 8, 90, 0, 0], "4": [6, 14, 80, 0, 0], "5": [4, 6, 90, 0, 0]},
            "2035": {"1": [2, 4, 45, 7, 42], "2": [2, 4, 45, 14, 36], "3": [2, 3, 45, 14, 36], "4": [2, 3, 45, 21, 30], "5": [2, 2, 45, 21, 30]},
            "2040": {"1": [2, 18, 60, 14, 6], "2": [1, 14, 60, 7, 18], "3": [1, 18, 54, 21, 6], "4": [1, 18, 54, 21, 6], "5": [2, 12, 60, 14, 12]},
            
        }
        
        if use_custom_mix:
            installed_capacities = {}
            for year_str, caps in custom_caps.items():
                caps_float = [float(c or 0) for c in caps]
                installed_capacities[str(year_str)] = {
                    "1": caps_float  # Only Option 1
                }


        # Fetch demand
        demand_resp = requests.get(f"http://localhost:5000/api/user_energy_demand/{user_id}")
        if demand_resp.status_code != 200:
            return jsonify({'error': 'Failed to fetch energy demand'}), 400

        region = data.get("region", "Region")

        all_demand_data = demand_resp.json()

        capacity_factors = {
            "Nuclear": 0.909, "Geothermal": 0.672, "Biomass": 0.671,
            "Coal": 0.589, "Natural Gas": 0.503, "Hydro": 0.405,
            "Wind": 0.15, "Solar": 0.12, "Hydrogen": 0.6, "Tidal": 0.3
        }

        def simulate_region(region_name):
            results = []
            energy_options = defaultdict(lambda: defaultdict(dict))

            region_projection_name = projections_by_region.get(region_name, projection_name)
            matched_projection = next((p for p in all_demand_data if p['name'] == region_projection_name), None)

            if not matched_projection:
                raise Exception(f'Selected demand projection not found for region {region_name}')

            energy_by_year = matched_projection.get('energy', {})


            for year_str, option_sets in installed_capacities.items():
                if '-' in year_str:
                    year = int(year_str.split('-')[0])
                else:
                    year = int(year_str)
                if not (start_year <= year <= end_year):
                    continue

                for option_str, capacity_row in option_sets.items():
                    option_index = int(option_str)
                    total_cost = 0
                    total_energy = 0
                    demand_for_year = float(energy_by_year.get(year_str, 0))

                    for source_index, installed_capacity in enumerate(capacity_row):
                        if source_index >= len(sources):
                            continue
                        if installed_capacity <= 0:
                            continue

                        source = sources[source_index]
                        source_type = source['type']
                        cf = capacity_factors.get(source_type, 0)
                        sizing_limit = float(source.get('sizing_limits', {}).get(year_str, 0) or 0)
                        
                        derating = float(source.get('derating_factor', 1.0))
                        scaling = float(source.get('scaling_factor', 1.0))
                        reliability_margin = 0.8

                        engineering_energy = (
                            (cf * sizing_limit * derating * scaling * 24 * 365) / reliability_margin
                        ) if cf > 0 else 0
                        
                        if demand_for_year > 0:
                            raw_percent = round(100 * engineering_energy / demand_for_year)
                            percent = min(raw_percent, 100)
                        else:
                            percent = 0



                        energy_generated = (demand_for_year * (installed_capacity / 100)) / (cf * 8760) if cf > 0 else 0
                        total_energy += energy_generated

                        capex = float(source.get('capital_cost', 0)) 
                        opex = float(source.get('om_cost', 0)) 
                        fuel_cost = float(source.get('fuel_price', 0))
                        lifetime = int(source.get('lifetime', 25))
                        crf = compute_crf(discount_rate, lifetime)
                        annualized_cost = (((capex * crf * installed_capacity) + (opex * installed_capacity)) / (8760 * cf)) + fuel_cost
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
                            'engineering_energy': round(engineering_energy, 2),
                            'percent': round(percent, 1)
                        })

                        energy_options[year_str][f"Option {option_index}"][source_type] = round(energy_generated, 2)

                    coe = (total_cost * 10000 / total_energy) if total_energy > 0 else 0
                    energy_options[year_str][f"Option {option_index}"]["COE"] = round(coe, 5)

            return results, energy_options, energy_by_year  

        # If MULTI mode
        # If MULTI mode
        if run_mode == "multi":
            results_by_region = {}
            all_results = []
            aggregated_options = defaultdict(lambda: defaultdict(dict))
            region_balances = {}

            # Run simulation per region
            for region in selected_regions:
                region_results, region_options, energy_by_year = simulate_region(region)
                results_by_region[region] = {
                    "results": region_results,
                    "energy_options": region_options
                }
                all_results.extend(region_results)

                # Calculate region net balance per year using energy_generated as supply
                region_balances[region] = {}
                for year in energy_by_year:
                    year_key = year
                    try:
                        year_int = int(year)
                    except ValueError:
                        year_int = int(year.split('-')[0])

                    # Sum energy_generated as total supply
                    total_generated = sum(
                        row['energy_generated'] for row in region_results if row['year'] == year_int
                    )
                    demand = float(energy_by_year[year])
                    balance = total_generated - 3000 # surplus (+) or deficit (-)
                    region_balances[region][year_key] = balance

                # Aggregate options
                for year, options in region_options.items():
                    for opt, values in options.items():
                        for key, val in values.items():
                            if key == "COE":
                                aggregated_options[year][opt].setdefault("COE_list", []).append(val)
                            else:
                                aggregated_options[year][opt][key] = aggregated_options[year][opt].get(key, 0) + val

            # Average COE
            for year in aggregated_options:
                for opt in aggregated_options[year]:
                    coe_list = aggregated_options[year][opt].pop("COE_list", [])
                    aggregated_options[year][opt]["COE"] = round(sum(coe_list) / len(coe_list), 5) if coe_list else 0

            # Energy sharing calculation
            energy_sharing = []

            # DEBUG: print region balances
            print("=== Region Balances per year ===")
            for r, balances in region_balances.items():
                print(f"{r}: {balances}")

            # Loop over all years present in balances
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
                            limit = transmission_limit_by_year.get(str(year), 100)
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
                            # Update balances
                            region_balances[from_region][year] -= sent
                            region_balances[to_region][year] += received
                            surplus -= sent
                            if surplus <= 0:
                                break  # Move to next from_region

            # DEBUG: print final sharing result
            print("=== Energy Sharing Calculated ===")
            print(energy_sharing)

            return jsonify({
                "selected_regions": selected_regions,
                "results": all_results,
                "results_by_region": results_by_region,
                "aggregated": {
                    "energy_options": aggregated_options
                },
                "energy_sharing": energy_sharing,
                "region_balances": region_balances,
            })


        # SINGLE mode
        else:
            region = data.get("region", "Region")
            results, energy_options, _ = simulate_region(region)
            return jsonify({
                "selected_regions": [region],
                "results": results,
                "energy_options": energy_options
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)})


from flask import jsonify, request
from collections import defaultdict

@app.route('/api/economic_analysis', methods=['POST'])
def economic_analysis():
    """
    Payload expects:
    {
      "results": [...],               # array returned by /api/run_simulation ("results" field)
      "years": [2025,2030,...]         # optional filter/order
    }
    """
    data = request.get_json() or {}
    results = data.get("results", [])
    years_filter = data.get("years")

    # Aggregate generation & demand
    gen_by_year = defaultdict(float)
    demand_by_year = defaultdict(float)
    seen_demand_keys = set()  # To avoid double counting

    for r in results:
        y = int(r["year"])
        gen_by_year[y] += float(r.get("energy_generated", 0))

        d = float(r.get("demand", 0))
        key = (y, r.get("option"), r.get("region"))
        if d > 0 and key not in seen_demand_keys:
            demand_by_year[y] += d
            seen_demand_keys.add(key)

    # Decide year order
    years = sorted(set(gen_by_year.keys()) | set(demand_by_year.keys()))
    if years_filter:
        years = [y for y in years if y in years_filter]

    # Build yearly data
    generation_data = []
    total_gen = total_demand = total_surplus = 0

    for y in years:
        g = round(gen_by_year.get(y, 0), 3)
        d = round(demand_by_year.get(y, 0), 3)
        s = round(g - d, 3)

        total_gen += g
        total_demand += d
        total_surplus += s

        generation_data.append({
            "year": y,
            "demand": d,
            "surplus": s,
            "generation": g
        })

    # Add Total row like in Excel
    generation_data.append({
        "year": "Total",
        "demand": round(total_demand, 3),
        "surplus": round(total_surplus, 3),
        "generation": round(total_gen, 3)
    })

    # Placeholder cash flow
    cash_flow_data = [{"year": y, "cash_flow": 0} for y in years if isinstance(y, int)]

    # Economic summary placeholders
    economic_summary = {
        "electricity_price": 0.1,
        "increasing_rate": 5,
        "net_present_cost": 0,
        "lcoe": 0.0
    }

    return jsonify({
        "generation_data": generation_data,
        "cash_flow": cash_flow_data,
        "summary": economic_summary
    })



if __name__ == '__main__':
    app.run(debug=True)