
namespace ext_ns {

class ExtClass {
public:
  ExtClass(int i) : i{i} {}

  int get() { return i; }

  void set(int i) { this->i = i; }

private:
  int i;
};

} // namespace ext_ns