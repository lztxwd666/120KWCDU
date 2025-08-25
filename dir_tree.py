import os


def generate_tree(path, indent=''):
    """生成目录树结构，忽略指定目录"""
    # 要忽略的目录列表
    ignore_dirs = ['.venv', 'etc', 'secret_key', '.git']

    tree = []
    for item in sorted(os.listdir(path)):  # 排序使输出更有序
        if item in ignore_dirs:
            # 显示目录但不展开内容
            tree.append(f"{indent}├── {item}/ (ignored)")
            continue

        full_path = os.path.join(path, item)
        if os.path.isdir(full_path):
            tree.append(f"{indent}├── {item}/")
            tree.append(generate_tree(full_path, indent + "│   "))
        else:
            tree.append(f"{indent}└── {item}")
    return '\n'.join(tree)


if __name__ == "__main__":
    project_root = os.path.dirname(os.path.abspath(__file__))
    tree_structure = generate_tree(project_root)
    print(tree_structure)
    # 可选：自动复制到剪贴板
    try:
        import pyperclip

        pyperclip.copy(tree_structure)
        print("\n目录结构已复制到剪贴板")
    except ImportError:
        print("\npyperclip 未安装，无法复制到剪贴板")
