from datetime import datetime, timezone
from app.extensions import db

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @classmethod
    def get_val(cls, key, default=None):
        try:
            setting = cls.query.filter_by(key=key).first()
            return setting.value if setting else default
        except Exception:
            return default

    @classmethod
    def set_val(cls, key, value, description=None):
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            setting = cls(key=key, value=str(value), description=description)
            db.session.add(setting)
        else:
            setting.value = str(value)
            if description:
                setting.description = description
        db.session.commit()
        return setting

def get_platform_fee_config():
    """
    Returns (fee_percent: float, fee_name: str) configured by Super Admin.
    Defaults to 2.0% and 'Platform Processing Fee'.
    """
    percent_str = SystemSetting.get_val('platform_fee_percent', '2.0')
    name_str = SystemSetting.get_val('platform_fee_name', 'Platform Processing Fee')
    try:
        fee_percent = float(percent_str)
        if fee_percent < 0:
            fee_percent = 0.0
    except (ValueError, TypeError):
        fee_percent = 2.0

    return fee_percent, (name_str or 'Platform Processing Fee')
