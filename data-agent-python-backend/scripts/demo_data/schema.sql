SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS refunds;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS promotions;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS order_promotions;
DROP TABLE IF EXISTS product_categories;
DROP TABLE IF EXISTS sales_channels;
DROP TABLE IF EXISTS regions;

CREATE TABLE users (
    id INT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE COMMENT '用户名',
    email VARCHAR(128) NOT NULL UNIQUE COMMENT '邮箱',
    province VARCHAR(32) NOT NULL COMMENT '常住省份',
    city VARCHAR(64) NOT NULL COMMENT '常住城市',
    membership_level ENUM('normal', 'silver', 'gold', 'platinum') NOT NULL DEFAULT 'normal' COMMENT '会员等级',
    age_group ENUM('18-24', '25-34', '35-44', '45-54', '55+') NOT NULL COMMENT '年龄段',
    created_at DATETIME NOT NULL COMMENT '注册时间',
    INDEX idx_users_location (province, city),
    INDEX idx_users_level (membership_level),
    INDEX idx_users_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

CREATE TABLE categories (
    id INT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE COMMENT '分类名称'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品分类表';

CREATE TABLE products (
    id INT PRIMARY KEY,
    category_id INT NOT NULL COMMENT '所属分类',
    sku VARCHAR(64) NOT NULL UNIQUE COMMENT '商品编码',
    name VARCHAR(128) NOT NULL COMMENT '商品名称',
    brand VARCHAR(64) NOT NULL COMMENT '品牌',
    price DECIMAL(12, 2) NOT NULL COMMENT '当前销售单价',
    cost_price DECIMAL(12, 2) NOT NULL COMMENT '当前成本单价',
    stock INT NOT NULL COMMENT '当前库存',
    status ENUM('active', 'inactive') NOT NULL DEFAULT 'active' COMMENT '商品状态',
    created_at DATETIME NOT NULL COMMENT '上架时间',
    CONSTRAINT fk_products_category FOREIGN KEY (category_id) REFERENCES categories (id),
    INDEX idx_products_category (category_id),
    INDEX idx_products_brand (brand),
    INDEX idx_products_price (price),
    INDEX idx_products_stock (stock)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品表';

CREATE TABLE promotions (
    id INT PRIMARY KEY,
    name VARCHAR(96) NOT NULL COMMENT '活动名称',
    promotion_type ENUM('percentage', 'fixed') NOT NULL COMMENT '优惠类型',
    start_date DATE NOT NULL COMMENT '开始日期',
    end_date DATE NOT NULL COMMENT '结束日期',
    discount_rate DECIMAL(5, 4) NOT NULL COMMENT '折扣比例',
    max_discount DECIMAL(12, 2) NOT NULL COMMENT '单笔最高优惠',
    min_order_amount DECIMAL(12, 2) NOT NULL DEFAULT 0 COMMENT '最低订单金额',
    INDEX idx_promotions_period (start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='营销活动表';

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '下单用户',
    promotion_id INT NULL COMMENT '主要营销活动',
    sales_channel ENUM('app', 'web', 'mini_program', 'store', 'marketplace') NOT NULL COMMENT '销售渠道',
    payment_method ENUM('alipay', 'wechat', 'bank_card', 'cash') NOT NULL COMMENT '支付方式',
    province VARCHAR(32) NOT NULL COMMENT '收货省份快照',
    city VARCHAR(64) NOT NULL COMMENT '收货城市快照',
    subtotal_amount DECIMAL(14, 2) NOT NULL COMMENT '优惠前商品金额',
    discount_amount DECIMAL(12, 2) NOT NULL DEFAULT 0 COMMENT '优惠金额',
    total_amount DECIMAL(14, 2) NOT NULL COMMENT '优惠后实付金额',
    status ENUM('completed', 'pending', 'cancelled') NOT NULL COMMENT '订单状态',
    order_date DATETIME NOT NULL COMMENT '下单时间',
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_orders_promotion FOREIGN KEY (promotion_id) REFERENCES promotions (id),
    INDEX idx_orders_user_date (user_id, order_date),
    INDEX idx_orders_date_status (order_date, status),
    INDEX idx_orders_channel_date (sales_channel, order_date),
    INDEX idx_orders_location (province, city)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL COMMENT '订单ID',
    product_id INT NOT NULL COMMENT '商品ID',
    quantity INT NOT NULL COMMENT '购买数量',
    unit_price DECIMAL(12, 2) NOT NULL COMMENT '下单时销售单价',
    unit_cost DECIMAL(12, 2) NOT NULL COMMENT '下单时成本单价',
    line_amount DECIMAL(14, 2) NOT NULL COMMENT '明细销售金额',
    CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders (id),
    CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products (id),
    INDEX idx_items_order (order_id),
    INDEX idx_items_product (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细表';

CREATE TABLE refunds (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL COMMENT '原订单ID',
    order_item_id BIGINT NULL COMMENT '部分退款对应的订单明细',
    refund_amount DECIMAL(14, 2) NOT NULL COMMENT '退款金额',
    reason VARCHAR(128) NOT NULL COMMENT '退款原因',
    status ENUM('approved', 'processing', 'rejected') NOT NULL COMMENT '退款状态',
    created_at DATETIME NOT NULL COMMENT '申请时间',
    CONSTRAINT fk_refunds_order FOREIGN KEY (order_id) REFERENCES orders (id),
    CONSTRAINT fk_refunds_item FOREIGN KEY (order_item_id) REFERENCES order_items (id),
    INDEX idx_refunds_order (order_id),
    INDEX idx_refunds_item (order_item_id),
    INDEX idx_refunds_status_date (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='退款记录表';

SET FOREIGN_KEY_CHECKS = 1;
