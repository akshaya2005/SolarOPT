from pipeline import energy_model, fetch_nsrdb, optimize, preprocess


def test_modules_import():
    assert fetch_nsrdb and preprocess and energy_model and optimize
