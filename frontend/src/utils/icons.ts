import {
  Box, Briefcase, Calendar, ChatDotRound, CircleCheck, CirclePlus, Cloudy, Coin,
  Connection, Cpu, Delete, Document, Edit, Files, Finished, FolderChecked, FolderOpened, Key,
  Lightning, Lock, Monitor, Notebook, Odometer, OfficeBuilding, Operation, Reading,
  SetUp, Share, Tickets, Tools, TrendCharts, User, UserFilled, View, Warning,
} from '@element-plus/icons-vue'
import type { Component } from 'vue'

/**
 * 动态字符串图标注册表
 * 来源：后端 _ICON_MAP（侧栏/仪表盘返回图标名）与 DataTable action.icon。
 * 按需引入模式下无全局图标注册，这些字符串图标需显式注册才能被 <component :is> 解析。
 */
export const dynamicIcons: Record<string, Component> = {
  Box,
  Briefcase,
  Calendar,
  ChatDotRound,
  CircleCheck,
  CirclePlus,
  Cloudy,
  Coin,
  Connection,
  Cpu,
  Delete,
  Document,
  Edit,
  Files,
  Finished,
  FolderChecked,
  FolderOpened,
  Key,
  Lightning,
  Lock,
  Monitor,
  Notebook,
  Odometer,
  OfficeBuilding,
  Operation,
  Reading,
  SetUp,
  Share,
  Tickets,
  Tools,
  TrendCharts,
  User,
  UserFilled,
  View,
  Warning,
}
