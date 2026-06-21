import os, json, tempfile, sys
sys.path.insert(0, '.')
from data_manager import DataManager, UserRole

tmpdir = tempfile.mkdtemp(prefix='lab_debug2_')
print(f'tmpdir: {tmpdir}')
dm = DataManager(data_dir=tmpdir)
dm.init_sample_data()

bad_templates = [
    {'name': '仪器不存在模板', 'instrument_code': 'INS-999', 'purpose': 't', 'default_duration_minutes': 60, 'reminder_minutes': 0, 'remark': '', 'applicable_persons': [], 'time_slots': [{'start_time': '09:00', 'end_time': '10:00'}]},
    {'name': '', 'instrument_code': 'INS-001', 'purpose': 't', 'default_duration_minutes': 60, 'reminder_minutes': 0, 'remark': '', 'applicable_persons': [], 'time_slots': []},
    {'name': '负责人不匹配模板', 'instrument_code': 'INS-001', 'purpose': 't', 'default_duration_minutes': 60, 'reminder_minutes': 0, 'remark': '', 'applicable_persons': ['不存在的人'], 'time_slots': [{'start_time': '09:00', 'end_time': '10:00'}]},
    {'name': '重复名称1', 'instrument_code': 'INS-001', 'purpose': 't', 'default_duration_minutes': 60, 'reminder_minutes': 0, 'remark': '', 'applicable_persons': [], 'time_slots': []},
    {'name': '重复名称1', 'instrument_code': 'INS-001', 'purpose': 't2', 'default_duration_minutes': 60, 'reminder_minutes': 0, 'remark': '', 'applicable_persons': [], 'time_slots': []},
    {'name': '非法时段模板', 'instrument_code': 'INS-001', 'purpose': 't', 'default_duration_minutes': 60, 'reminder_minutes': 0, 'remark': '', 'applicable_persons': [], 'time_slots': [{'start_time': '25:00', 'end_time': '26:00'}]},
]
bad_json_path = os.path.join(tmpdir, 'bad.json')
with open(bad_json_path, 'w', encoding='utf-8') as f:
    json.dump(bad_templates, f, ensure_ascii=False, indent=2)

result = dm.import_templates_json(bad_json_path, overwrite=False, user_role=UserRole.ADMIN)
print(f'total={result.total_count}')
print(f'success={result.success_count}')
print(f'failed={result.failed_count}')
if hasattr(result, 'success_names'):
    print(f'success_names={result.success_names}')
print('errors:')
for e in result.errors:
    print(f'  - {e}')
