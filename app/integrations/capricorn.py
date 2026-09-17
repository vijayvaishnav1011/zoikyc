"""
Backward compatibility proxy for CapricornESignProvider.
The primary Capricorn E-Sign integration provider is now located in app.esign.capricorn.
"""
import requests
from app.esign.capricorn import CapricornESignProvider

__all__ = ['CapricornESignProvider', 'requests']
