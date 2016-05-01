from sqlalchemy import Column, ForeignKey, String, Integer, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import INET, MACADDR

from sipa.model.sqlalchemy import db


class Account(db.Model):
    __tablename__ = 'account'
    __bind_key__ = 'hss'

    account = Column(String(16), primary_key=True, nullable=False)
    name = Column(String(255), nullable=False)

    # Not needed now, staying in the code for https://git.io/vw1bH though.
    # finance_balance = Column(Numeric(5, 2), nullable=False, default=0)

    traffic_balance = Column(BigInteger, nullable=False, default=10000000000)
    access_id = Column('access', Integer, ForeignKey('access.id'))

    ips = relationship('IP')
    macs = relationship('Mac')


class Access(db.Model):
    __tablename__ = 'access'
    __bind_key__ = 'hss'

    id = Column(Integer, primary_key=True, nullable=False)
    building = Column(String(16))  # e.g. "HSS46"
    floor = Column(String(8))  # e.g. "0"
    flat = Column(String(8))  # e.g. "1"
    room = Column(String(8))  # e.g. "b"

    users = relationship('Account', backref='access')


class IP(db.Model):
    __tablename__ = 'ip'
    __bind_key__ = 'hss'

    ip = Column(INET, primary_key=True)
    account = Column(String(16), ForeignKey('account.account'))


class Mac(db.Model):
    __tablename__ = 'mac'
    __bind_key__ = 'hss'

    id = Column(Integer, primary_key=True)
    mac = Column(MACADDR, nullable=False)
    account = Column(String(16), ForeignKey('account.account'))
