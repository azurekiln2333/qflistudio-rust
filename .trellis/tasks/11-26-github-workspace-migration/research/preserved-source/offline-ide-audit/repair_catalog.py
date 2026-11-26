import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_text(value, pairs):
    if isinstance(value, str):
        for before, after in pairs:
            value = value.replace(before, after)
        return value
    if isinstance(value, list):
        return [replace_text(item, pairs) for item in value]
    if isinstance(value, dict):
        return {key: replace_text(item, pairs) for key, item in value.items()}
    return value


for path in sorted((ROOT / 'tool/rust_content').glob('topics_*.json')):
    source = path.read_text(encoding='utf-8')
    topics = json.loads(source)
    assert source == json.dumps(topics, ensure_ascii=False, indent=2) + '\n'
    for index, topic in enumerate(topics):
        if topic['id'] == 13:
            topic = replace_text(topic, [('sum_of_squares(10000)', 'sum_of_squares(100)'),
                                         ('sum_of_squares(10_000)', 'sum_of_squares(100)')])
            topic['explain'] += (' 本例在移动解释器中用 100 个元素保留预热、多轮采样与结果校验的完整流程。'
                                 'Miri 的单调时钟是虚拟时钟，不能用它评价手机硬件性能；'
                                 '正式测量应在桌面原生 release 构建中扩大输入规模并记录环境。')
        elif topic['id'] == 62:
            topic = replace_text(topic, [('Some((ref name, ref age))', 'Some(&(ref name, ref age))')])
            topic['explain'] += (' Rust 2024 中，默认绑定模式已经是引用时不能再写冗余的 ref。'
                                 '本题显式匹配 Some(&(ref name, ref age))：& 解构元组引用，'
                                 'ref 再借用字段，既不移动 String，也明确展示显式绑定。')
        elif topic['id'] in {157, 158, 159, 166}:
            topic = replace_text(topic, [('#[no_mangle]', '#[unsafe(no_mangle)]'),
                                         ('extern "C" {', 'unsafe extern "C" {')])
            topic['explain'] += (' 当前 Rust 2024 要求将导出符号属性写为 #[unsafe(no_mangle)]，'
                                 '外部声明块写为 unsafe extern "C"；符号唯一性和函数签名仍需由作者保证。')
        elif topic['id'] == 161:
            topic = replace_text(topic, [('0..20_000', '0..200'), ('i % 500', 'i % 20'),
                                         ('a.len(), 500', 'a.len(), 20'),
                                         ('b.len(), 500', 'b.len(), 20'),
                                         ('count=500', 'count=20'),
                                         ('1..=100_000', '1..=1_000'),
                                         ('让差异大到足以稳定观察', '比较算法结构，并校验两种实现的结果一致')])
            topic['explain'] += (' 移动端用 200 个输入、20 个不同值展示去重过程，'
                                 '练习用 1000 个元素比较求和，保留两种算法与确定性断言。'
                                 '小样本和 Miri 虚拟计时不适合得出性能排名；'
                                 '实际基准应在桌面原生 release 构建中扩大数据规模。')
        topics[index] = topic
    path.write_text(json.dumps(topics, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
