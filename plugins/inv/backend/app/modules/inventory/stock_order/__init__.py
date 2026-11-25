"""统一库存单据：单据类型 inv_stock_order_type、单据 inv_stock_order + 明细 inv_stock_order_line、确认记账。

入库、出库、调拨、借出、归还、报损、盘点调整都是同一张单据，按类型区分；
确认（记账）由 posting.post_order 完成，是改变库存余额与写入库存流水的唯一入口。
"""
