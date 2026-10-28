"""Multi-turn risk: risk accumulated across turns (running maximum of the model score over prefixes)."""


def turn_scores(clf, turns):
    """Model score after each turn k, computed on turns[:k]."""
    return [float(clf.score(turns[:k])) for k in range(1, len(turns) + 1)]


def accumulate(scores):
    out, m = [], 0.0
    for s in scores:
        m = max(m, s)
        out.append(m)
    return out


def accumulated_risk(clf, turns):
    return accumulate(turn_scores(clf, turns))[-1] if turns else 0.0
