def merge_issues(

    security,

    quality,

    performance,

    testing,

    architecture
):

    all_issues = []

    all_issues.extend(security)

    all_issues.extend(quality)

    all_issues.extend(performance)

    all_issues.extend(testing)

    all_issues.extend(architecture)

    return all_issues