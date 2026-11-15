"""가벼운 분석 도구: k-평균 군집 (numpy만 사용)."""

import numpy as np
import pandas as pd


def kmeans(X, k, seed=0, iters=100):
    """표준화된 X(n×d)를 k개로 나눈다. 초기 중심은 1차원 분위수(결정적)로 잡는다."""
    rng = np.random.default_rng(seed)
    n = len(X)
    order = np.argsort(X[:, 0])
    centers = X[order[np.linspace(0, n - 1, k + 2)[1:-1].round().astype(int)]].astype(float)
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        dist = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new = dist.argmin(axis=1)
        if np.array_equal(new, labels) and _ > 0:
            break
        labels = new
        for j in range(k):
            members = X[labels == j]
            centers[j] = members.mean(axis=0) if len(members) else X[rng.integers(n)]
    return labels, centers


def cluster_countries(df, columns, k):
    """df에 cluster(1=최대 군) 열을 붙여 돌려준다. 로그 척도로 표준화해 군집한다."""
    d = df.dropna(subset=columns).copy()
    d = d[(d[columns] > 0).all(axis=1)]
    if len(d) < k:
        d["cluster"] = 1
        return d
    X = np.log10(d[columns].to_numpy(dtype=float))
    X = (X - X.mean(axis=0)) / X.std(axis=0).clip(1e-9)
    labels, centers = kmeans(X, k)
    # 중심의 첫 번째 축(선택한 기준) 기준으로 큰 군이 1번이 되도록 번호를 다시 매긴다
    rank = {old: new + 1 for new, old in enumerate(np.argsort(-centers[:, 0]))}
    d["cluster"] = pd.Series(labels, index=d.index).map(rank)
    return d


def thresholds(d, column):
    """1차원 기준일 때 인접 군 사이의 경계값(아래 군의 최댓값과 위 군의 최솟값의 기하평균)."""
    bounds = []
    groups = d.groupby("cluster")[column]
    ks = sorted(groups.groups)
    for upper, lower in zip(ks[:-1], ks[1:]):
        hi_min, lo_max = groups.get_group(upper).min(), groups.get_group(lower).max()
        bounds.append((upper, lower, float(np.sqrt(hi_min * lo_max)) if hi_min > 0 and lo_max > 0 else float(hi_min)))
    return bounds
