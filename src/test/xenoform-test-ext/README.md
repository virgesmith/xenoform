# xenoform-test-ext

Separate pybind11 extension module, used for testing xenoform functions using C++ objects with python bindings.
Crucially ensuring that such types can be passed by reference.

STL containers bound as opaque types do not work.
