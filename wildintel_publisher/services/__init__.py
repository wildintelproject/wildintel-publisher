# Importing these registers their ProductAdapter (see services.product) as
# a side effect — done here, once, so hfh/zenodo/b2share's product.get_adapter
# calls always find "camtrapdp"/"yolo" regardless of which submodule of
# services gets imported first (CLI command, web backend, or a test).
from wildintel_publisher.services import camtrapdp_adapter as _camtrapdp_adapter  # noqa: E402,F401
from wildintel_publisher.services import yolo_adapter as _yolo_adapter  # noqa: E402,F401
