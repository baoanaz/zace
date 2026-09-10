#include "service.hpp"

namespace app {

int call_service(Service &service) { return service.process(1); }

}  // namespace app
