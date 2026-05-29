MODULE_ORDER = {
    "test_00_full_positive_flow.py": 0,
    "test_01_login_module.py": 1,
    "test_02_email_module.py": 2,
    "test_03_mobile_module.py": 3,
    "test_04_address_module.py": 4,
    "test_05_nominee_module.py": 5,
    "test_06_bank_module.py": 6,
    "test_07_segment_module.py": 7,
    "test_08_income_module.py": 8,
    "test_09_dis_slip_module.py": 9,
    "test_10_service_status_module.py": 10,
}


def pytest_collection_modifyitems(config, items):
    items.sort(key=lambda item: (MODULE_ORDER.get(item.path.name, 999), item.nodeid))
