from xenoform import ReturnValuePolicy, compile


@compile(return_value_policy=ReturnValuePolicy.Reference, verbose=True)
def rvp_function(a: int, b: int) -> float:  # ty: ignore[empty-body]
    """
    return a + b;
    """


def test_explicit_rvp() -> None:
    # just check it can be called
    assert rvp_function(2, 2) == 4


if __name__ == "__main__":
    test_explicit_rvp()
