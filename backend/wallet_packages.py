"""Wallet top-up packages (in TRY)."""

WALLET_PACKAGES = [
    {"id": "topup_100", "amount_try": 100.0, "bonus_try": 0.0, "label": "Deneme"},
    {"id": "topup_250", "amount_try": 250.0, "bonus_try": 25.0, "label": "Başlangıç"},
    {"id": "topup_500", "amount_try": 500.0, "bonus_try": 75.0, "label": "Profesyonel", "popular": True},
    {"id": "topup_1000", "amount_try": 1000.0, "bonus_try": 200.0, "label": "Uzman"},
    {"id": "topup_2500", "amount_try": 2500.0, "bonus_try": 750.0, "label": "Kurumsal"},
]

def get_package(pkg_id: str):
    return next((p for p in WALLET_PACKAGES if p["id"] == pkg_id), None)
