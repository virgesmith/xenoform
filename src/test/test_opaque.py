# from typing import Annotated


# # pollutes every module
# class VecBool(Export, cpp_type="std::vector<bool>"): ...  # , includes=["<pybind11/stl.h>"]): ...


# class VecDouble(Export, cpp_type="std::vector<double>"): ...  # , includes=["<pybind11/stl.h>"]): ...


# # TODO py::bind_...
# # class MapStrDouble(Export, cpp_type="std::unordered_map<std::string, double>", includes=["<pybind11/stl.h>"]): ...


# @compile()
# def len_vecbool(v: list[bool]) -> int:  # ty: ignore[empty-body]
#     """
#     return v.size();
#     """


# # still need to annotate FFS
# @compile()
# def len_vecdouble(v: Annotated[VecDouble, "std::vector<double>"]) -> int:  # ty: ignore[empty-body]
#     """
#     return v.size();
#     """


# if __name__ == "__main__":
#     v = VecBool([True] * 10)
#     print(dir(v))
#     print(len_vecdouble(VecDouble([0.0])))
#     print(Export.opaques())
#     print(Export.bindings())
