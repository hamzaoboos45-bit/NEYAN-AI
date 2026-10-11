"""
backend/security — Phase One authentication hardening.

Modules:
    csrf.py            — CSRF token generation + validation
    brute_force.py      — login attempt tracking / account lockout
    remember_me.py       — persistent "remember me" login tokens
    password_reset.py    — forgot/reset password token architecture

Every module here is additive: nothing in routes/ or backend/chatbot.py
is replaced, only wrapped with extra protection.
"""
