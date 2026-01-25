#include "module.h"

#include <pybind11/pybind11.h>
#include <pybind11/stl_bind.h>

namespace py = pybind11;
using namespace ext_ns;

PYBIND11_MAKE_OPAQUE(std::vector<uint64_t>)


PYBIND11_MODULE(_xenoform_test_ext, m) {

  py::class_<ExtClass>(m, "ExtClass")
      .def(py::init<int>())
      .def("get", &ExtClass::get)
      .def("set", &ExtClass::set);


  py::bind_vector<std::vector<uint64_t>>(m, "vec_uint64_t");

  m.def("mutate", [](std::vector<uint64_t>& v) { for(auto& n: v) ++n; });

}