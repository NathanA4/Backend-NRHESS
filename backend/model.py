from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import JSON

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = {'schema': 'nrhess'}
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    energy_projections = db.relationship('EnergyDemandProjection', backref='user', cascade='all, delete-orphan')
    daily_profiles = db.relationship('DailyProfile', backref='user', cascade='all, delete-orphan')


class EnergyDemandProjection(db.Model):
    __tablename__ = 'energydemandprojection'
    __table_args__ = {'schema': 'nrhess'}
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    base_demand = db.Column(db.Float, nullable=False)
    growth_rate = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('nrhess.users.id'), nullable=False)


class DailyProfile(db.Model):
    __tablename__ = 'dailyprofile'
    __table_args__ = {'schema': 'nrhess'}
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    hourly_values = db.Column(db.Text, nullable=False)
    variability_day = db.Column(db.Float, default=0.0)
    variability_time = db.Column(db.Float, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey('nrhess.users.id'), nullable=False)

class Location(db.Model):
    __tablename__ = 'locations'
    __table_args__ = {'schema': 'nrhess'}
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    region = db.Column(db.String(100), nullable=False, default='Durham')
    solar_irradiance = db.Column(db.Float, nullable=False)
    wind_speed = db.Column(db.Float, nullable=False)
    solar_profile_dry = db.Column(JSON)
    solar_profile_rainy = db.Column(JSON)
    wind_profile_dry = db.Column(JSON)
    wind_profile_rainy = db.Column(JSON)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'region': self.region, 
            'solar_irradiance': self.solar_irradiance,
            'wind_speed': self.wind_speed,
            'solar_profile_dry': self.solar_profile_dry,
            'solar_profile_rainy': self.solar_profile_rainy,
            'wind_profile_dry': self.wind_profile_dry,
            'wind_profile_rainy': self.wind_profile_rainy,
        }
