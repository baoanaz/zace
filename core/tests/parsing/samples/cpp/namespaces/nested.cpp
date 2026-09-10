#include "nested.hpp"

namespace outer {
namespace inner {

Widget::Widget() : value_(0) {}

Widget::~Widget() {}

void Widget::run() { compute(value_); }

int Widget::compute(int value) const { return value * 2; }

}  // namespace inner
}  // namespace outer

void outer::inner::Widget::reset() {}
