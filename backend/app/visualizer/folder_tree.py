def build_folder_tree(issues):
    tree = {}

    for issue in issues:
        path_parts = issue.file.split("/")
        current = tree

        for folder in path_parts[:-1]:
            if folder not in current:
                current[folder] = {}
            current = current[folder]

        filename = path_parts[-1]
        entry = {
            "severity": issue.severity,
            "category": issue.category,
            "problem": issue.issue,
            "recommendation": issue.suggestion,
        }

        if filename not in current:
            current[filename] = []
        elif not isinstance(current[filename], list):
            current[filename] = [current[filename]]

        current[filename].append(entry)

    return tree
