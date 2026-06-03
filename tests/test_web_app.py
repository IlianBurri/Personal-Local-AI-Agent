from ui.web_app import hash_password, verify_password, render_login_page, render_setup_page


def test_password_hash_roundtrip():
    hashed = hash_password('super-secret')
    assert hashed['password_salt']
    assert hashed['password_hash']
    assert verify_password(hashed['password_salt'], hashed['password_hash'], 'super-secret')
    assert not verify_password(hashed['password_salt'], hashed['password_hash'], 'wrong-password')


def test_auth_pages_include_expected_copy():
    login_page = render_login_page('Invalid password.')
    setup_page = render_setup_page()
    assert 'Invalid password.' in login_page
    assert 'Create a local password' in setup_page
