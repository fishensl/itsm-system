# -*- coding: utf-8 -*-
"""数据库模型包（按域分模块；本文件全量 re-export，外部导入路径不变）

schema 演进由 Alembic（migrations/）接管，模型仅声明当前结构。
"""
from models.base import db  # noqa: F401
from models.user import (  # noqa: F401
    Department, User, CustomerCategory, FormDraft, UserDashboardPreference,
    UserPermission, Permission, Role, RolePermission, user_regions)
from models.customer import Region, Customer  # noqa: F401
from models.device import (  # noqa: F401
    Device, DeviceFirmware, DeviceCredential, DeviceInterface, CustomField,
    PasswordHistory, DeviceType, DeviceSubType, NetworkType, Brand)
from models.inspection import (  # noqa: F401
    task_device_template_link, InspectionDeviceTemplate, InspectionTaskTemplate,
    InspectionTemplate, Inspector, InspectionTask, Inspection)
from models.ticket import FaultType, Ticket, TicketLog, Fault  # noqa: F401
from models.knowledge import KnowledgeBase, KnowledgeAttachment  # noqa: F401
from models.spare import SparePart, SpareStock, PurchaseOrder, SalesOrder, StockMovement  # noqa: F401
from models.sales import Opportunity, Quotation, Contract, Project  # noqa: F401
from models.misc import AIConfig, DeviceConfigBackup, Topology, DeviceCollectTask, SubmissionVersion, SubmissionAsset  # noqa: F401
from models.rack import Rack, RackInstall  # noqa: F401
from models.notification import Notification  # noqa: F401
from models.audit import AuditLog  # noqa: F401
from models.setting import SystemSetting  # noqa: F401
